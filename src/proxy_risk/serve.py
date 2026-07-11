"""Production HTTP evaluate API — shadow/live Proxy-Risk gateway."""

from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import FastAPI, Request, status

from inst_spine.health_probes import ledger_chain_ready, readiness_payload, redis_ready_from_env, sqlite_db_ready
from inst_spine.http_lifecycle import error_envelope, json_response, make_lifespan
from inst_spine.ingress_guard import install_body_size_limit_middleware
from inst_spine.ledger import AppendOnlyLedger
from inst_spine.middleware import install_api_key_middleware, install_proxy_client_auth_middleware
from inst_spine.rates import (
    MemoryIdempotencyBackend,
    MemoryTokenBucketBackend,
    idempotency_backend_from_env,
    token_bucket_backend_from_env,
)
from proxy_risk.router import GateDecision, ProxyRequest, ProxyRiskGateway

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("proxy_risk.serve")


class RuntimeState:
    def __init__(self) -> None:
        self.ledger_db = os.getenv("PROXY_RISK_DATABASE", "data/proxy_risk_ledger.sqlite")
        self.shadow_mode = os.getenv("PROXY_RISK_SHADOW", "1") != "0"
        self.ledger: AppendOnlyLedger | None = None
        self.gateway: ProxyRiskGateway | None = None


state = RuntimeState()


def _force_memory_backends() -> bool:
    return os.getenv("INST_FORCE_MEMORY_BACKENDS", "").strip().lower() in ("1", "true", "yes")


def _production_backends() -> tuple[Any, Any]:
    if _force_memory_backends():
        return MemoryTokenBucketBackend(), MemoryIdempotencyBackend()
    return token_bucket_backend_from_env(), idempotency_backend_from_env()


def _gateway() -> ProxyRiskGateway:
    if state.gateway is None:
        if state.ledger is not None:
            state.ledger.stop_async_writer(flush=True)
            state.ledger.close()
        state.ledger = AppendOnlyLedger(state.ledger_db, async_writes=True)
        state.ledger.start_async_writer()
        rate_backend, idempotency = _production_backends()
        state.gateway = ProxyRiskGateway(
            ledger=state.ledger,
            shadow_mode=state.shadow_mode,
            rate_backend=rate_backend,
            idempotency=idempotency,
        )
    return state.gateway


def _startup() -> None:
    if not os.getenv("PROXY_RISK_API_KEY", "").strip() and os.getenv("PROXY_RISK_API_TOKEN", "").strip():
        os.environ["PROXY_RISK_API_KEY"] = os.environ["PROXY_RISK_API_TOKEN"]
    gw = _gateway()
    logger.info(
        "Proxy-Risk online db=%s shadow=%s upstream=%s redis=%s",
        state.ledger_db,
        state.shadow_mode,
        gw.upstream_base or "(unset)",
        "memory_forced" if _force_memory_backends() else (os.getenv("INST_REDIS_URL") or "memory"),
    )


def _shutdown() -> None:
    if state.ledger:
        state.ledger.stop_async_writer(flush=True)


app = FastAPI(
    title="Proxy-Risk — outbound API firewall",
    lifespan=make_lifespan(_startup, _shutdown),
)
install_api_key_middleware(app, env_var="PROXY_RISK_API_KEY")
install_proxy_client_auth_middleware(app)
install_body_size_limit_middleware(app)


@app.get("/health")
async def health() -> dict[str, Any]:
    gw = _gateway()
    return {
        "ok": True,
        "product": "proxy-risk",
        "shadow": state.shadow_mode,
        "upstream_base": gw.upstream_base or None,
        "auth_required": bool(
            os.getenv("PROXY_RISK_API_KEY", "").strip() or os.getenv("PROXY_RISK_API_TOKEN", "").strip()
        ),
        "redis_profile": bool(os.getenv("INST_REDIS_URL", "").strip()) and not _force_memory_backends(),
    }


@app.get("/ready")
async def ready() -> Any:
    ledger_db_ok, ledger_db_detail = sqlite_db_ready(state.ledger_db)
    chain_ok, chain_detail = ledger_chain_ready(state.ledger_db)
    redis_ok, redis_detail = redis_ready_from_env()
    body = readiness_payload(
        product="proxy-risk",
        checks={
            "ledger_db": (ledger_db_ok, ledger_db_detail),
            "ledger_chain": (chain_ok, chain_detail),
            "redis_profile": (redis_ok, redis_detail),
        },
        extra={"shadow": state.shadow_mode},
    )
    return json_response(body, status_code=200 if body["ready"] else 503)


@app.post("/v1/evaluate")
async def evaluate(request: Request) -> Any:
    try:
        body = await request.json()
    except Exception:
        return error_envelope(code="INVALID_JSON", message="request body must be JSON")

    if not isinstance(body, dict):
        return error_envelope(code="INVALID_JSON", message="JSON object required")

    client_id = str(body.get("client_id") or "").strip()
    method = str(body.get("method") or "POST").strip()
    path = str(body.get("path") or "/").strip()
    if not client_id:
        return error_envelope(code="SCHEMA_ERROR", message="client_id required")
    if not method:
        return error_envelope(code="SCHEMA_ERROR", message="method required")
    if not path:
        return error_envelope(code="SCHEMA_ERROR", message="path required")

    req = ProxyRequest(
        client_id=client_id,
        method=method,
        path=path,
        body=body.get("body") if isinstance(body.get("body"), dict) else {},
        idempotency_key=body.get("idempotency_key"),
        reference_price=body.get("reference_price"),
        model_features=body.get("model_features") if isinstance(body.get("model_features"), dict) else None,
    )
    resp = await _gateway().evaluate(req)
    payload = {
        "ok": resp.decision == GateDecision.APPROVE,
        "decision": resp.decision.value,
        "reason": resp.reason,
        "upstream_status": resp.upstream_status,
        "upstream_body": resp.upstream_body,
        "shadow": state.shadow_mode,
    }
    if resp.decision == GateDecision.REJECT:
        return json_response(payload, status_code=status.HTTP_429_TOO_MANY_REQUESTS)
    if resp.decision == GateDecision.KILL:
        return json_response(payload, status_code=status.HTTP_503_SERVICE_UNAVAILABLE)
    return json_response(payload)


def main() -> None:
    import uvicorn

    host = os.getenv("PROXY_RISK_HOST", "127.0.0.1")
    port = int(os.getenv("PROXY_RISK_PORT", "18443"))
    uvicorn.run("proxy_risk.serve:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
