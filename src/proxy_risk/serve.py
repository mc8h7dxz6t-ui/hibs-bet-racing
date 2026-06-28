"""Production HTTP evaluate API — shadow/live Proxy-Risk gateway."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from fastapi import FastAPI, Request, Response, status

from inst_spine.health_probes import readiness_payload, redis_ready_from_env, sqlite_db_ready
from inst_spine.ledger import AppendOnlyLedger
from inst_spine.middleware import install_api_key_middleware
from inst_spine.rates import MemoryIdempotencyBackend, MemoryTokenBucketBackend
from proxy_risk.router import GateDecision, ProxyRequest, ProxyRiskGateway

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("proxy_risk.serve")

app = FastAPI(title="Proxy-Risk — outbound API firewall")
install_api_key_middleware(app, env_var="PROXY_RISK_API_KEY")


class RuntimeState:
    def __init__(self) -> None:
        self.ledger_db = os.getenv("PROXY_RISK_DATABASE", "data/proxy_risk_ledger.sqlite")
        self.shadow_mode = os.getenv("PROXY_RISK_SHADOW", "1") != "0"
        self.ledger: AppendOnlyLedger | None = None
        self.gateway: ProxyRiskGateway | None = None


state = RuntimeState()


def _gateway() -> ProxyRiskGateway:
    if state.gateway is None:
        if state.ledger is not None:
            state.ledger.stop_async_writer(flush=True)
            state.ledger.close()
        state.ledger = AppendOnlyLedger(state.ledger_db, async_writes=True)
        state.ledger.start_async_writer()
        state.gateway = ProxyRiskGateway(
            ledger=state.ledger,
            shadow_mode=state.shadow_mode,
            rate_backend=MemoryTokenBucketBackend(),
            idempotency=MemoryIdempotencyBackend(),
        )
    return state.gateway


@app.on_event("startup")
async def startup() -> None:
    if not os.getenv("PROXY_RISK_API_KEY", "").strip() and os.getenv("PROXY_RISK_API_TOKEN", "").strip():
        os.environ["PROXY_RISK_API_KEY"] = os.environ["PROXY_RISK_API_TOKEN"]
    _gateway()
    logger.info(
        "Proxy-Risk online db=%s shadow=%s upstream=%s",
        state.ledger_db,
        state.shadow_mode,
        _gateway().upstream_base or "(unset)",
    )


@app.on_event("shutdown")
async def shutdown() -> None:
    if state.ledger:
        state.ledger.stop_async_writer(flush=True)


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
    }


@app.get("/ready")
async def ready() -> Response:
    ledger_ok, ledger_detail = sqlite_db_ready(state.ledger_db)
    redis_ok, redis_detail = redis_ready_from_env()
    body = readiness_payload(
        product="proxy-risk",
        checks={
            "ledger_db": (ledger_ok, ledger_detail),
            "redis_optional": (redis_ok, redis_detail),
        },
        extra={"shadow": state.shadow_mode},
    )
    code = status.HTTP_200_OK if body["ready"] else status.HTTP_503_SERVICE_UNAVAILABLE
    return Response(content=json.dumps(body), status_code=code, media_type="application/json")


@app.post("/v1/evaluate", response_model=None)
async def evaluate(request: Request) -> dict[str, Any] | Response:
    try:
        body = await request.json()
    except (json.JSONDecodeError, ValueError):
        return Response(
            content='{"error":"invalid JSON body"}',
            status_code=status.HTTP_400_BAD_REQUEST,
            media_type="application/json",
        )
    if not isinstance(body, dict):
        return Response(
            content='{"error":"body must be a JSON object"}',
            status_code=status.HTTP_400_BAD_REQUEST,
            media_type="application/json",
        )

    req = ProxyRequest(
        client_id=str(body.get("client_id") or "anon"),
        method=str(body.get("method") or "POST"),
        path=str(body.get("path") or "/"),
        body=body.get("body") if isinstance(body.get("body"), dict) else {},
        idempotency_key=body.get("idempotency_key"),
        reference_price=body.get("reference_price"),
        model_features=body.get("model_features") if isinstance(body.get("model_features"), dict) else None,
    )
    gw = _gateway()
    resp = await gw.evaluate(req)
    payload = {
        "decision": resp.decision.value,
        "reason": resp.reason,
        "upstream_status": resp.upstream_status,
        "upstream_body": resp.upstream_body,
        "shadow": state.shadow_mode,
    }
    if resp.decision == GateDecision.REJECT:
        return Response(
            content=json.dumps(payload),
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            media_type="application/json",
        )
    if resp.decision == GateDecision.KILL:
        return Response(
            content=json.dumps(payload),
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            media_type="application/json",
        )
    return payload


def main() -> None:
    import uvicorn

    host = os.getenv("PROXY_RISK_HOST", "127.0.0.1")
    port = int(os.getenv("PROXY_RISK_PORT", "18443"))
    uvicorn.run("proxy_risk.serve:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
