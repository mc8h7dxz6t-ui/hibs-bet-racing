"""Agent Ledger HTTP middleware — authorize-before-invoke for agent frameworks."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from agent_ledger.gate import AgentActionRequest, gate_from_paths
from agent_ledger.permits import PermitStore
from inst_spine.health_probes import ledger_chain_ready, readiness_payload, sqlite_db_ready
from inst_spine.http_lifecycle import json_response, make_lifespan
from inst_spine.ingress_guard import install_body_size_limit_middleware
from inst_spine.middleware import install_api_key_middleware

_permit_sweep_task: asyncio.Task[None] | None = None


def _permit_sweep_interval_seconds() -> int:
    raw = os.getenv("AGENT_LEDGER_PERMIT_SWEEP_SECONDS", "300").strip()
    try:
        return max(30, int(raw))
    except ValueError:
        return 300


def _ledger_db() -> Path:
    return Path(os.getenv("AGENT_LEDGER_DB", "data/agent_ledger.sqlite"))


def _permit_db() -> Path:
    raw = os.getenv("AGENT_LEDGER_PERMITS_DB", "").strip()
    return Path(raw) if raw else _ledger_db().with_name(_ledger_db().stem + "_permits.sqlite")


def _startup() -> None:
    global _permit_sweep_task
    swept = PermitStore(_permit_db()).sweep_expired()
    if swept:
        import logging

        logging.getLogger("agent_ledger.serve").info("swept %s expired permits on startup", swept)


async def _async_startup() -> None:
    _startup()
    global _permit_sweep_task
    interval = _permit_sweep_interval_seconds()

    async def _loop() -> None:
        import logging

        log = logging.getLogger("agent_ledger.serve")
        while True:
            await asyncio.sleep(interval)
            try:
                swept = PermitStore(_permit_db()).sweep_expired()
                if swept:
                    log.info("periodic permit sweep released %s expired permits", swept)
            except Exception as exc:
                log.error("PERMIT_SWEEP_FAILED: %s", exc)

    _permit_sweep_task = asyncio.create_task(_loop(), name="agent-ledger-permit-sweep")


async def _async_shutdown() -> None:
    global _permit_sweep_task
    if _permit_sweep_task is not None:
        _permit_sweep_task.cancel()
        try:
            await _permit_sweep_task
        except asyncio.CancelledError:
            pass
        _permit_sweep_task = None


def _shutdown() -> None:
    return None


app = FastAPI(
    title="Agent Ledger — runtime tool authorization",
    lifespan=make_lifespan(_async_startup, _async_shutdown),
)
install_api_key_middleware(app, env_var="AGENT_LEDGER_API_KEY")
install_body_size_limit_middleware(app)


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "ok": True,
        "product": "agent-ledger",
        "auth_required": bool(os.getenv("AGENT_LEDGER_API_KEY", "").strip()),
    }


@app.get("/ready")
async def ready() -> Any:
    ledger_ok, ledger_detail = sqlite_db_ready(_ledger_db())
    permit_ok, permit_detail = sqlite_db_ready(_permit_db())
    chain_ok, chain_detail = ledger_chain_ready(_ledger_db())
    body = readiness_payload(
        product="agent-ledger",
        checks={
            "ledger_db": (ledger_ok, ledger_detail),
            "permit_db": (permit_ok, permit_detail),
            "ledger_chain": (chain_ok, chain_detail),
        },
    )
    return json_response(body, status_code=200 if body["ready"] else 503)


@app.post("/v1/authorize")
async def authorize(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "invalid JSON"}, status_code=400)
    if not isinstance(body, dict):
        return JSONResponse({"ok": False, "error": "JSON object required"}, status_code=400)
    tool_name = str(body.get("tool_name") or "").strip()
    if not tool_name:
        return JSONResponse({"ok": False, "error": "tool_name required"}, status_code=400)
    gw = gate_from_paths(ledger_db=_ledger_db(), permit_db=_permit_db())
    resp = gw.authorize(
        AgentActionRequest(
            agent_id=str(body.get("agent_id") or "agent"),
            tool_name=tool_name,
            arguments=body.get("arguments") or {},
            session_id=str(body.get("session_id") or ""),
            idempotency_key=body.get("idempotency_key"),
        )
    )
    code = status.HTTP_200_OK if resp.decision.value == "permit" else status.HTTP_403_FORBIDDEN
    return JSONResponse({"ok": resp.decision.value == "permit", **resp.to_dict()}, status_code=code)


@app.post("/v1/complete")
async def complete(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "invalid JSON"}, status_code=400)
    if not isinstance(body, dict):
        return JSONResponse({"ok": False, "error": "JSON object required"}, status_code=400)
    permit_id = str(body.get("permit_id") or "").strip()
    if not permit_id:
        return JSONResponse({"ok": False, "error": "permit_id required"}, status_code=400)
    gw = gate_from_paths(ledger_db=_ledger_db(), permit_db=_permit_db())
    resp = gw.complete(permit_id, result=body.get("result"))
    code = status.HTTP_200_OK if resp.decision.value == "complete" else status.HTTP_409_CONFLICT
    return JSONResponse({"ok": resp.decision.value == "complete", **resp.to_dict()}, status_code=code)


def main() -> None:
    import uvicorn

    host = os.getenv("AGENT_LEDGER_HOST", "127.0.0.1")
    port = int(os.getenv("AGENT_LEDGER_PORT", "8792"))
    uvicorn.run("agent_ledger.serve:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
