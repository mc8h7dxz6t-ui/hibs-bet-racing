"""Agent Ledger HTTP middleware — authorize-before-invoke for agent frameworks."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from agent_ledger.gate import AgentActionRequest, gate_from_paths

app = FastAPI(title="Agent Ledger — runtime tool authorization")


def _ledger_db() -> Path:
    return Path(os.getenv("AGENT_LEDGER_DB", "data/agent_ledger.sqlite"))


def _permit_db() -> Path:
    raw = os.getenv("AGENT_LEDGER_PERMITS_DB", "").strip()
    return Path(raw) if raw else _ledger_db().with_name(_ledger_db().stem + "_permits.sqlite")


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"ok": True, "service": "agent-ledger"}


@app.post("/v1/authorize")
async def authorize(request: Request) -> JSONResponse:
    body = await request.json()
    if not isinstance(body, dict):
        return JSONResponse({"ok": False, "error": "JSON object required"}, status_code=400)
    gw = gate_from_paths(ledger_db=_ledger_db(), permit_db=_permit_db())
    resp = gw.authorize(
        AgentActionRequest(
            agent_id=str(body.get("agent_id") or "agent"),
            tool_name=str(body.get("tool_name") or ""),
            arguments=body.get("arguments") or {},
            session_id=str(body.get("session_id") or ""),
            idempotency_key=body.get("idempotency_key"),
        )
    )
    code = status.HTTP_200_OK if resp.decision.value == "permit" else status.HTTP_403_FORBIDDEN
    return JSONResponse({"ok": resp.decision.value == "permit", **resp.to_dict()}, status_code=code)


@app.post("/v1/complete")
async def complete(request: Request) -> JSONResponse:
    body = await request.json()
    if not isinstance(body, dict):
        return JSONResponse({"ok": False, "error": "JSON object required"}, status_code=400)
    permit_id = str(body.get("permit_id") or "")
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
