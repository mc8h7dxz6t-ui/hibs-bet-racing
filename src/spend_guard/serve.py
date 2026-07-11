"""OpenAI-compatible spend gateway — reserve before dispatch, settle on usage."""

from __future__ import annotations

import json
import logging
import os
import uuid
import asyncio
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, Request, Response, status

from inst_spine.health_probes import (
    ledger_chain_ready,
    readiness_payload,
    redis_ready_from_env,
    sqlite_db_ready,
    wallet_state_ready,
)
from inst_spine.http_lifecycle import make_lifespan
from inst_spine.ledger import AppendOnlyLedger
from inst_spine.ingress_guard import install_body_size_limit_middleware
from inst_spine.middleware import install_api_key_middleware
from spend_guard.cost import actual_cost_from_usage, estimate_reserve_cost
from spend_guard.gateway import SpendGuardGateway, SpendRequest
from spend_guard.wallet_factory import open_wallet

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("spend_guard.serve")

_UPSTREAM_TIMEOUT = httpx.Timeout(60.0, connect=10.0)


class RuntimeState:
    gateway: SpendGuardGateway | None = None
    ledger: AppendOnlyLedger | None = None
    wallet_db: str = os.getenv("SPEND_GUARD_WALLET_DB", "data/spend_guard_wallet.sqlite")
    ledger_db: str = os.getenv("SPEND_GUARD_LEDGER_DB", "data/spend_guard.sqlite")
    upstream_base: str = os.getenv("SPEND_GUARD_UPSTREAM_BASE", "https://api.openai.com/v1").rstrip("/")
    upstream_api_key: str = os.getenv("SPEND_GUARD_UPSTREAM_API_KEY", os.getenv("OPENAI_API_KEY", ""))
    shadow_mode: bool = os.getenv("SPEND_GUARD_SHADOW", "0") == "1"
    mock_upstream: bool = os.getenv("SPEND_GUARD_MOCK_UPSTREAM", "0") == "1"


state = RuntimeState()
_hold_reap_task: asyncio.Task[None] | None = None


def _hold_reap_interval_seconds() -> int:
    raw = os.getenv("SPEND_HOLD_REAP_SECONDS", "300").strip()
    try:
        return max(30, int(raw))
    except ValueError:
        return 300


def _gateway() -> SpendGuardGateway:
    if state.gateway is None:
        if state.ledger is not None:
            state.ledger.stop_async_writer(flush=True)
            state.ledger.close()
            state.ledger = None
        ledger_path = Path(state.ledger_db)
        wallet = open_wallet(state.wallet_db, ledger_db=ledger_path)
        state.ledger = AppendOnlyLedger(ledger_path, async_writes=True)
        state.ledger.start_async_writer()
        state.gateway = SpendGuardGateway(
            wallet=wallet,
            ledger=state.ledger,
            shadow_mode=state.shadow_mode,
        )
    return state.gateway


def _startup() -> None:
    _gateway()
    gw = state.gateway
    if gw is not None:
        reaped = gw.wallet.reap_expired_holds()
        if reaped:
            logger.info("reaped %s expired spend holds on startup", reaped)
    logger.info(
        "Spend Guard gateway online wallet=%s ledger=%s shadow=%s mock=%s",
        state.wallet_db,
        state.ledger_db,
        state.shadow_mode,
        state.mock_upstream,
    )


async def _async_startup() -> None:
    global _hold_reap_task
    _startup()
    interval = _hold_reap_interval_seconds()

    async def _loop() -> None:
        while True:
            await asyncio.sleep(interval)
            try:
                gw = _gateway()
                reaped = gw.wallet.reap_expired_holds()
                if reaped:
                    logger.info("periodic hold reap released %s stranded holds", reaped)
            except Exception as exc:
                logger.error("HOLD_REAP_FAILED: %s", exc)

    _hold_reap_task = asyncio.create_task(_loop(), name="spend-guard-hold-reap")


async def _async_shutdown() -> None:
    global _hold_reap_task
    if _hold_reap_task is not None:
        _hold_reap_task.cancel()
        try:
            await _hold_reap_task
        except asyncio.CancelledError:
            pass
        _hold_reap_task = None
    if state.ledger:
        state.ledger.stop_async_writer(flush=True)


app = FastAPI(
    title="Spend Guard — OpenAI-compatible gateway",
    lifespan=make_lifespan(_async_startup, _async_shutdown),
)
install_api_key_middleware(app, env_var="SPEND_GUARD_API_KEY", skip_prefixes=("/static",))
install_body_size_limit_middleware(app)


@app.get("/health")
async def health() -> dict[str, Any]:
    wallet = _gateway().wallet.to_dict()
    return {
        "ok": True,
        "product": "spend-guard",
        "shadow": state.shadow_mode,
        "mock_upstream": state.mock_upstream,
        "wallet": wallet,
        "auth_required": bool(os.getenv("SPEND_GUARD_API_KEY", "").strip()),
    }


@app.get("/ready")
async def ready() -> Response:
    wallet_file_ok, wallet_file_detail = sqlite_db_ready(state.wallet_db)
    wallet_ok, wallet_detail = wallet_state_ready(state.wallet_db)
    ledger_ok, ledger_detail = sqlite_db_ready(state.ledger_db)
    chain_ok, chain_detail = ledger_chain_ready(state.ledger_db)
    redis_ok, redis_detail = redis_ready_from_env()
    body = readiness_payload(
        product="spend-guard",
        checks={
            "wallet_file": (wallet_file_ok, wallet_file_detail),
            "wallet_state": (wallet_ok, wallet_detail),
            "ledger_db": (ledger_ok, ledger_detail),
            "ledger_chain": (chain_ok, chain_detail),
            "redis_profile": (redis_ok, redis_detail),
        },
        extra={"mock_upstream": state.mock_upstream},
    )
    code = status.HTTP_200_OK if body["ready"] else status.HTTP_503_SERVICE_UNAVAILABLE
    return Response(content=json.dumps(body), status_code=code, media_type="application/json")


@app.get("/v1/models")
async def list_models() -> dict[str, Any]:
    return {
        "object": "list",
        "data": [
            {"id": "gpt-4o-mini", "object": "model", "owned_by": "spend-guard"},
            {"id": "gpt-4o", "object": "model", "owned_by": "spend-guard"},
            {"id": "demo-model", "object": "model", "owned_by": "spend-guard"},
        ],
    }


def _error_response(code: int, error_type: str, message: str) -> Response:
    return Response(
        content=json.dumps({"error": {"type": error_type, "message": message}}),
        status_code=code,
        media_type="application/json",
    )


async def _mock_chat_completion(body: dict[str, Any]) -> dict[str, Any]:
    model = str(body.get("model") or "demo-model")
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "Spend Guard mock response."},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20},
    }


async def _forward_upstream(body: dict[str, Any], request: Request) -> tuple[int, dict[str, Any] | None, str]:
    if state.mock_upstream or not state.upstream_api_key:
        return 200, await _mock_chat_completion(body), ""

    headers = {
        "Authorization": f"Bearer {state.upstream_api_key}",
        "Content-Type": "application/json",
    }
    rid = request.headers.get("X-Request-Id")
    if rid:
        headers["X-Request-Id"] = rid
    async with httpx.AsyncClient(timeout=_UPSTREAM_TIMEOUT) as client:
        resp = await client.post(f"{state.upstream_base}/chat/completions", json=body, headers=headers)
    try:
        payload = resp.json()
    except Exception:
        payload = None
    return resp.status_code, payload if isinstance(payload, dict) else None, resp.text


@app.post("/v1/chat/completions", response_model=None)
async def chat_completions(request: Request) -> Response:
    gw = _gateway()
    try:
        body = await request.json()
    except Exception:
        return _error_response(status.HTTP_400_BAD_REQUEST, "invalid_request", "invalid JSON body")
    if not isinstance(body, dict):
        return _error_response(status.HTTP_400_BAD_REQUEST, "invalid_request", "body must be object")

    request_id = (
        request.headers.get("X-Request-Id")
        or request.headers.get("X-Idempotency-Key")
        or f"sg-{uuid.uuid4().hex}"
    )
    estimated, model = estimate_reserve_cost(body)
    reserve_resp = gw.reserve(
        SpendRequest(
            request_id=request_id,
            estimated_cost=estimated,
            service=model,
            metadata={"route": "/v1/chat/completions"},
        )
    )
    decision = reserve_resp.decision.value
    if decision == "locked":
        return _error_response(
            status.HTTP_409_CONFLICT,
            "wallet_locked",
            reserve_resp.reason or "wallet locked",
        )
    if decision == "reject":
        return _error_response(status.HTTP_402_PAYMENT_REQUIRED, "spend_rejected", reserve_resp.reason or "reserve rejected")

    hold_id = reserve_resp.hold_id or ""
    try:
        status_code, upstream, raw = await _forward_upstream(body, request)
    except Exception as exc:
        if hold_id and not state.shadow_mode:
            gw.wallet.release(hold_id)
        return _error_response(
            status.HTTP_502_BAD_GATEWAY,
            "upstream_error",
            str(exc),
        )
    if status_code >= 400 or upstream is None:
        if hold_id and not state.shadow_mode:
            gw.wallet.release(hold_id)
        return Response(
            content=raw or json.dumps({"error": {"message": "upstream failed"}}),
            status_code=status_code if status_code >= 400 else status.HTTP_502_BAD_GATEWAY,
            media_type="application/json",
        )

    usage = upstream.get("usage") if isinstance(upstream.get("usage"), dict) else None
    actual = actual_cost_from_usage(usage, model=model)
    if actual <= 0:
        actual = min(estimated, estimated * 0.9)
    if hold_id:
        settle_resp = gw.settle(hold_id, actual_cost=actual, request_id=request_id, service=model)
        if settle_resp.decision.value == "locked":
            upstream = dict(upstream)
            upstream["_spend_guard"] = {"warning": "wallet_locked_after_settle", "reason": settle_resp.reason}

    upstream = dict(upstream)
    upstream["_spend_guard"] = {
        **upstream.get("_spend_guard", {}),
        "request_id": request_id,
        "reserved": estimated,
        "settled": actual,
        "hold_id": hold_id,
    }
    return Response(content=json.dumps(upstream), status_code=status.HTTP_200_OK, media_type="application/json")


def main() -> None:
    import uvicorn

    host = os.getenv("SPEND_GUARD_HOST", "127.0.0.1")
    port = int(os.getenv("SPEND_GUARD_PORT", "8789"))
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
