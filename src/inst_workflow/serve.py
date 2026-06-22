"""Inst++ Workflow UI — FastAPI backend for Compliance + Proxy-Risk."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from compliance_log.ingest import log_decision
from inst_spine.check import build_compliance_context, run_institutional_check
from inst_spine.export import build_audit_bundle, verify_audit_bundle
from inst_spine.ledger import AppendOnlyLedger
from proxy_risk.router import ProxyRequest, ProxyRiskGateway

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Inst++ Workflow Console", version="1.0.0")


class RuntimeState:
    compliance_db: Path = Path(os.getenv("INST_COMPLIANCE_DB", "data/demo/compliance.sqlite"))
    proxy_db: Path = Path(os.getenv("INST_PROXY_DB", "data/demo/proxy.sqlite"))
    export_dir: Path = Path(os.getenv("INST_EXPORT_DIR", "data/demo/ui_exports"))
    proxy_shadow: bool = os.getenv("INST_PROXY_SHADOW", "1") != "0"
    upstream_base: str = os.getenv("PROXY_RISK_UPSTREAM_BASE", "https://httpbin.org")


state = RuntimeState()
_cached_proxy_gateway: ProxyRiskGateway | None = None
_cached_proxy_ledger: AppendOnlyLedger | None = None


def reset_proxy_runtime() -> None:
    """Reset proxy gateway singleton (tests / CLI reconfigure)."""
    global _cached_proxy_gateway, _cached_proxy_ledger
    if _cached_proxy_ledger is not None:
        _cached_proxy_ledger.stop_async_writer(flush=True)
    _cached_proxy_gateway = None
    _cached_proxy_ledger = None


def _proxy_gateway() -> ProxyRiskGateway:
    global _cached_proxy_gateway, _cached_proxy_ledger
    if _cached_proxy_gateway is None:
        _cached_proxy_ledger = AppendOnlyLedger(_proxy_db(), async_writes=True)
        _cached_proxy_ledger.start_async_writer()
        _cached_proxy_gateway = ProxyRiskGateway(
            ledger=_cached_proxy_ledger,
            shadow_mode=state.proxy_shadow,
            upstream_base=state.upstream_base,
        )
    return _cached_proxy_gateway


def _compliance_db() -> Path:
    state.compliance_db.parent.mkdir(parents=True, exist_ok=True)
    return state.compliance_db


def _proxy_db() -> Path:
    state.proxy_db.parent.mkdir(parents=True, exist_ok=True)
    return state.proxy_db


@app.on_event("shutdown")
async def shutdown() -> None:
    reset_proxy_runtime()


class IngestBody(BaseModel):
    snapshot: dict[str, Any]
    outcome: dict[str, Any] = Field(default_factory=dict)
    actor: str = "workflow-ui"


class ProxyEvaluateBody(BaseModel):
    client_id: str = "broker-demo"
    method: str = "POST"
    path: str = "/orders"
    body: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = None
    reference_price: float | None = None
    live: bool = False


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "ok": True,
        "products": ["compliance-logger", "proxy-risk"],
        "compliance_db": str(state.compliance_db),
        "proxy_db": str(state.proxy_db),
        "proxy_shadow": state.proxy_shadow,
    }


@app.get("/api/demo/compliance-snapshot")
async def demo_compliance_snapshot() -> dict[str, Any]:
    path = Path("docs/demo_snapshot.json")
    if not path.is_file():
        raise HTTPException(404, "demo snapshot missing")
    return json.loads(path.read_text(encoding="utf-8"))


@app.get("/api/demo/proxy-request")
async def demo_proxy_request() -> dict[str, Any]:
    path = Path("docs/demo_proxy_request.json")
    if not path.is_file():
        raise HTTPException(404, "demo proxy request missing")
    return json.loads(path.read_text(encoding="utf-8"))


@app.get("/api/compliance/ledger")
async def compliance_ledger() -> dict[str, Any]:
    ledger = AppendOnlyLedger(_compliance_db())
    entries = ledger.list_entries()
    return {"entries": entries, "verify": ledger.verify(), "count": len(entries)}


@app.post("/api/compliance/ingest")
async def compliance_ingest(body: IngestBody) -> dict[str, Any]:
    entry = log_decision(
        snapshot=body.snapshot,
        outcome=body.outcome,
        actor=body.actor,
        database=_compliance_db(),
    )
    return {"ok": True, "entry": entry}


@app.post("/api/compliance/check")
async def compliance_check() -> dict[str, Any]:
    ledger = AppendOnlyLedger(_compliance_db())
    ctx = build_compliance_context(ledger, run_f9=True)
    report = run_institutional_check(ledger=ledger, context=ctx, run_f9=False)
    return report.to_dict()


@app.post("/api/compliance/export")
async def compliance_export() -> dict[str, Any]:
    state.export_dir.mkdir(parents=True, exist_ok=True)
    out = state.export_dir / "compliance_bundle"
    tar = state.export_dir / "compliance_bundle.tar"
    result = build_audit_bundle(
        _compliance_db(),
        out_dir=out,
        tarball_path=tar,
        product="compliance-logger",
    )
    if not result.ok:
        raise HTTPException(400, result.validation.message)
    return {
        "ok": True,
        "product": "compliance-logger",
        "bundle_sha256": result.bundle_sha256,
        "tarball": str(result.tarball_path),
        "institutional_passed": result.institutional_passed,
    }


@app.post("/api/compliance/verify-bundle")
async def compliance_verify_bundle() -> dict[str, Any]:
    tar = state.export_dir / "compliance_bundle.tar"
    if not tar.is_file():
        raise HTTPException(404, "export bundle first")
    result = verify_audit_bundle(tar)
    return {
        "ok": result.ok,
        "genesis_ok": result.genesis_ok,
        "chain_ok": result.chain_ok,
        "lamport_ok": result.lamport_ok,
        "bundle_sha256_ok": result.bundle_sha256_ok,
        "institutional_passed": result.institutional_passed,
        "message": result.message,
        "details": result.details,
    }


@app.get("/api/proxy/ledger")
async def proxy_ledger() -> dict[str, Any]:
    ledger = AppendOnlyLedger(_proxy_db())
    entries = ledger.list_entries()
    proxy_rows = [e for e in entries if e.get("event_type") == "proxy_request"]
    return {"entries": entries, "proxy_rows": proxy_rows, "verify": ledger.verify()}


@app.post("/api/proxy/evaluate")
async def proxy_evaluate(body: ProxyEvaluateBody) -> dict[str, Any]:
    gw = _proxy_gateway()
    prev_shadow = gw.shadow_mode
    gw.shadow_mode = not body.live
    try:
        resp = await gw.evaluate(
            ProxyRequest(
                client_id=body.client_id,
                method=body.method,
                path=body.path,
                body=body.body,
                idempotency_key=body.idempotency_key,
                reference_price=body.reference_price,
            )
        )
    finally:
        gw.shadow_mode = prev_shadow
    return {
        "decision": resp.decision.value,
        "reason": resp.reason,
        "upstream_status": resp.upstream_status,
        "upstream_body": resp.upstream_body,
        "live": body.live,
    }


@app.post("/api/proxy/check")
async def proxy_check() -> dict[str, Any]:
    ledger = AppendOnlyLedger(_proxy_db())
    ctx = build_compliance_context(ledger, run_f9=True)
    report = run_institutional_check(ledger=ledger, context=ctx, run_f9=False)
    return report.to_dict()


@app.post("/api/proxy/export")
async def proxy_export() -> dict[str, Any]:
    state.export_dir.mkdir(parents=True, exist_ok=True)
    out = state.export_dir / "proxy_bundle"
    tar = state.export_dir / "proxy_bundle.tar"
    result = build_audit_bundle(
        _proxy_db(),
        out_dir=out,
        tarball_path=tar,
        product="proxy-risk",
    )
    if not result.ok:
        raise HTTPException(400, result.validation.message)
    return {
        "ok": True,
        "product": "proxy-risk",
        "bundle_sha256": result.bundle_sha256,
        "tarball": str(result.tarball_path),
        "institutional_passed": result.institutional_passed,
    }


@app.post("/api/proxy/verify-bundle")
async def proxy_verify_bundle() -> dict[str, Any]:
    tar = state.export_dir / "proxy_bundle.tar"
    if not tar.is_file():
        raise HTTPException(404, "export bundle first")
    result = verify_audit_bundle(tar)
    return {
        "ok": result.ok,
        "message": result.message,
        "details": result.details,
        "institutional_passed": result.institutional_passed,
    }


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
