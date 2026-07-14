"""Workflow UI — FastAPI backend for Proof Console (12 SKUs) + Compliance + Proxy."""

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
from inst_workflow.catalog import PRODUCT_CATALOG, catalog_by_id, list_catalog
from inst_workflow.demo_bootstrap import bootstrap_all, bootstrap_product
from inst_workflow.proof_ingest import (
    demo_payload,
    ingest_product_async,
    ingest_schema,
    supports_guided_ingest,
)
from proxy_risk.router import ProxyRequest, ProxyRiskGateway

from inst_spine.middleware import install_api_key_middleware
from inst_spine.ingress_guard import install_body_size_limit_middleware
from inst_spine.health_probes import readiness_payload
from inst_spine.production_profile import (
    postgres_ha_check,
    production_profile_enabled,
    redis_production_check,
)

STATIC_DIR = Path(__file__).parent / "static"
VALID_PRODUCTS = frozenset({"compliance", "proxy", "both"})

app = FastAPI(title="Workflow Console", version="1.0.0")
install_api_key_middleware(
    app,
    env_var="INST_WORKFLOW_API_KEY",
    skip_paths=frozenset({"/health", "/ready", "/", "/api/config"}),
)
install_body_size_limit_middleware(
    app,
    skip_paths=frozenset({"/health", "/ready", "/", "/api/config", "/static"}),
)


def normalize_product(value: str) -> str:
    product = (value or "both").strip().lower()
    if product not in VALID_PRODUCTS:
        raise ValueError(f"product must be one of: {', '.join(sorted(VALID_PRODUCTS))}")
    return product


class RuntimeState:
    compliance_db: Path = Path(os.getenv("INST_COMPLIANCE_DB", "data/demo/compliance.sqlite"))
    proxy_db: Path = Path(os.getenv("INST_PROXY_DB", "data/demo/proxy.sqlite"))
    export_dir: Path = Path(os.getenv("INST_EXPORT_DIR", "data/demo/ui_exports"))
    demo_dir: Path = Path(os.getenv("PORTFOLIO_DEMO_DIR", "data/demo/portfolio"))
    proxy_shadow: bool = os.getenv("INST_PROXY_SHADOW", "1") != "0"
    upstream_base: str = os.getenv("PROXY_RISK_UPSTREAM_BASE", "https://httpbin.org")
    product: str = normalize_product(os.getenv("INST_WORKFLOW_PRODUCT", "both"))
    active_proof_product: str = os.getenv("INST_PROOF_PRODUCT", "compliance")
    default_tab: str = os.getenv("INST_WORKFLOW_DEFAULT_TAB", "arch")


def _product_enabled(name: str) -> bool:
    if state.product == "both":
        return True
    return state.product == name


def _require_product(name: str) -> None:
    if not _product_enabled(name):
        raise HTTPException(404, f"{name} workflow not enabled (product={state.product})")


def _active_products() -> list[str]:
    if state.product == "both":
        return ["compliance-logger", "proxy-risk"]
    if state.product == "compliance":
        return ["compliance-logger"]
    return ["proxy-risk"]


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
    catalog = list_catalog(demo_dir=state.demo_dir)
    seeded = sum(1 for c in catalog if c.get("database_present"))
    return {
        "ok": True,
        "product": state.product,
        "products": _active_products(),
        "proof_catalog": len(PRODUCT_CATALOG),
        "active_proof_product": state.active_proof_product,
        "compliance_db": str(state.compliance_db),
        "proxy_db": str(state.proxy_db),
        "demo_dir": str(state.demo_dir),
        "proxy_shadow": state.proxy_shadow,
        "portfolio_seeded": seeded,
        "portfolio_total": len(PRODUCT_CATALOG),
    }


@app.get("/ready")
async def ready() -> dict[str, Any]:
    """K8s readiness — Proof Console usable when portfolio is seeded."""
    from fastapi.responses import JSONResponse

    catalog = list_catalog(demo_dir=state.demo_dir)
    seeded = sum(1 for c in catalog if c.get("database_present"))
    portfolio_ok = seeded >= len(PRODUCT_CATALOG)
    checks: dict[str, tuple[bool, str]] = {
        "portfolio_seeded": (
            portfolio_ok,
            f"{seeded}/{len(PRODUCT_CATALOG)} seeded",
        ),
    }
    if production_profile_enabled():
        redis_ok, redis_detail = redis_production_check()
        pg_ok, pg_detail = postgres_ha_check(os.getenv("INST_POSTGRES_DSN", ""))
        checks["redis_profile"] = (redis_ok, redis_detail)
        checks["postgres_ha"] = (pg_ok, pg_detail)
    body = readiness_payload(
        product="inst-workflow",
        checks=checks,
        extra={
            "demo_dir": str(state.demo_dir),
            "production_profile": production_profile_enabled(),
            "portfolio_seeded": seeded,
            "portfolio_total": len(PRODUCT_CATALOG),
        },
    )
    status_code = 200 if body["ready"] else 503
    return JSONResponse(content=body, status_code=status_code)


@app.get("/api/products")
async def products_catalog() -> dict[str, Any]:
    return {
        "catalog": list_catalog(demo_dir=state.demo_dir),
        "active": state.active_proof_product,
        "demo_dir": str(state.demo_dir),
    }


class ProofSelectBody(BaseModel):
    product_id: str


class ProofIngestBody(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)


@app.post("/api/proof/{product_id}/bootstrap")
async def proof_bootstrap(product_id: str) -> dict[str, Any]:
    entry = _proof_entry(product_id)
    result = bootstrap_product(entry, demo_dir=state.demo_dir, skip_live=True)
    if not result["ok"]:
        raise HTTPException(400, detail=result)
    return result


@app.post("/api/proof/bootstrap-all")
async def proof_bootstrap_all() -> dict[str, Any]:
    results = bootstrap_all(demo_dir=state.demo_dir, skip_live=True)
    ok = all(r["ok"] for r in results)
    return {
        "ok": ok,
        "seeded": sum(1 for r in results if r["ok"]),
        "total": len(results),
        "results": results,
    }


@app.post("/api/proof/verify-all")
async def proof_verify_all() -> dict[str, Any]:
    from inst_spine.export import verify_audit_bundle

    results: list[dict[str, Any]] = []
    failed = 0
    for entry in PRODUCT_CATALOG:
        tar = entry.export_tarball(state.export_dir)
        if not tar.is_file():
            tar = state.demo_dir / f"{entry.bundle_name}.tar"
        row: dict[str, Any] = {
            "id": entry.id,
            "sku": entry.sku,
            "tarball": str(tar),
            "present": tar.is_file(),
        }
        if not tar.is_file():
            row.update({"ok": False, "message": "tarball missing — export or make demo-all"})
            failed += 1
            results.append(row)
            continue
        verify = verify_audit_bundle(tar)
        row.update(
            {
                "ok": verify.ok,
                "institutional_passed": verify.institutional_passed,
                "message": verify.message,
            }
        )
        if not verify.ok:
            failed += 1
        results.append(row)
    return {
        "ok": failed == 0,
        "verified_ok": sum(1 for r in results if r.get("ok")),
        "total": len(PRODUCT_CATALOG),
        "results": results,
    }


@app.post("/api/proof/select")
async def proof_select(body: ProofSelectBody) -> dict[str, Any]:
    entry = catalog_by_id(body.product_id)
    if entry is None:
        raise HTTPException(404, f"unknown product: {body.product_id}")
    state.active_proof_product = entry.id
    return {"ok": True, "active": entry.to_dict(demo_dir=state.demo_dir)}


def _proof_entry(product_id: str | None = None):
    pid = product_id or state.active_proof_product
    entry = catalog_by_id(pid)
    if entry is None:
        raise HTTPException(404, f"unknown product: {pid}")
    return entry


def _proof_db(entry) -> Path:
    db = entry.db_path(state.demo_dir)
    if entry.id == "compliance":
        db = state.compliance_db
    elif entry.id == "proxy":
        db = state.proxy_db
    db.parent.mkdir(parents=True, exist_ok=True)
    return db


@app.get("/api/proof/{product_id}/demo-payload")
async def proof_demo_payload(product_id: str) -> dict[str, Any]:
    entry = _proof_entry(product_id)
    if not supports_guided_ingest(entry.id):
        raise HTTPException(404, f"guided ingest not available for {entry.id}")
    return {
        "ok": True,
        "product_id": entry.id,
        "sku": entry.sku,
        "schema": ingest_schema(entry),
        "payload": demo_payload(entry, demo_dir=state.demo_dir),
    }


@app.post("/api/proof/{product_id}/ingest")
async def proof_ingest(product_id: str, body: ProofIngestBody) -> dict[str, Any]:
    entry = _proof_entry(product_id)
    if not supports_guided_ingest(entry.id):
        raise HTTPException(404, f"guided ingest not available for {entry.id}")
    try:
        result = await ingest_product_async(
            entry,
            body.payload,
            demo_dir=state.demo_dir,
            database=_proof_db(entry),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(400, f"ingest failed: {exc}") from exc
    return result


@app.get("/api/proof/{product_id}/ledger")
async def proof_ledger(product_id: str) -> dict[str, Any]:
    entry = _proof_entry(product_id)
    db = _proof_db(entry)
    if not db.is_file():
        return {"entries": [], "verify": {"ok": True}, "count": 0, "database": str(db)}
    ledger = AppendOnlyLedger(db)
    entries = ledger.list_entries()
    return {"entries": entries, "verify": ledger.verify(), "count": len(entries), "database": str(db)}


@app.post("/api/proof/{product_id}/check")
async def proof_check(product_id: str) -> dict[str, Any]:
    entry = _proof_entry(product_id)
    db = _proof_db(entry)
    if not db.is_file():
        raise HTTPException(404, f"database missing — run: make demo-all ({db})")
    ledger = AppendOnlyLedger(db)
    ctx = build_compliance_context(ledger, run_f9=True)
    report = run_institutional_check(ledger=ledger, context=ctx, run_f9=False)
    return report.to_dict()


@app.post("/api/proof/{product_id}/export")
async def proof_export(product_id: str) -> dict[str, Any]:
    entry = _proof_entry(product_id)
    db = _proof_db(entry)
    if not db.is_file():
        raise HTTPException(404, f"database missing — run: make demo-all ({db})")
    state.export_dir.mkdir(parents=True, exist_ok=True)
    out = state.export_dir / entry.bundle_name
    tar = entry.export_tarball(state.export_dir)
    result = build_audit_bundle(db, out_dir=out, tarball_path=tar, product=entry.sku)
    if not result.ok:
        raise HTTPException(400, result.validation.message)
    return {
        "ok": True,
        "product": entry.sku,
        "bundle_sha256": result.bundle_sha256,
        "tarball": str(result.tarball_path),
        "institutional_passed": result.institutional_passed,
    }


@app.post("/api/proof/{product_id}/verify-bundle")
async def proof_verify(product_id: str) -> dict[str, Any]:
    entry = _proof_entry(product_id)
    tar = entry.export_tarball(state.export_dir)
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


@app.get("/api/config")
async def workflow_config() -> dict[str, Any]:
    titles = {
        "compliance": "Compliance Logger — Workflow Console",
        "proxy": "Proxy-Risk Gateway — Workflow Console",
        "both": "Workflow Console",
    }
    badges = {
        "compliance": "Compliance Logger",
        "proxy": "Proxy-Risk Gateway",
        "both": "Compliance Logger · Proxy-Risk Gateway",
    }
    if state.product == "both":
        default_tab = state.default_tab if state.default_tab in {"arch", "proof"} else "arch"
    else:
        default_tab = state.product
    return {
        "product": state.product,
        "title": titles[state.product],
        "badge": badges[state.product],
        "default_tab": default_tab,
        "tabs": {
            "arch": state.product == "both",
            "proof": True,
            "compliance": _product_enabled("compliance"),
            "proxy": _product_enabled("proxy"),
        },
        "proof": {
            "active": state.active_proof_product,
            "catalog": list_catalog(demo_dir=state.demo_dir),
        },
    }


@app.get("/api/demo/compliance-snapshot")
async def demo_compliance_snapshot() -> dict[str, Any]:
    _require_product("compliance")
    path = Path("docs/demo_snapshot.json")
    if not path.is_file():
        raise HTTPException(404, "demo snapshot missing")
    return json.loads(path.read_text(encoding="utf-8"))


@app.get("/api/demo/proxy-request")
async def demo_proxy_request() -> dict[str, Any]:
    _require_product("proxy")
    path = Path("docs/demo_proxy_request.json")
    if not path.is_file():
        raise HTTPException(404, "demo proxy request missing")
    return json.loads(path.read_text(encoding="utf-8"))


@app.get("/api/compliance/ledger")
async def compliance_ledger() -> dict[str, Any]:
    _require_product("compliance")
    ledger = AppendOnlyLedger(_compliance_db())
    entries = ledger.list_entries()
    return {"entries": entries, "verify": ledger.verify(), "count": len(entries)}


@app.post("/api/compliance/ingest")
async def compliance_ingest(body: IngestBody) -> dict[str, Any]:
    _require_product("compliance")
    entry = log_decision(
        snapshot=body.snapshot,
        outcome=body.outcome,
        actor=body.actor,
        database=_compliance_db(),
    )
    return {"ok": True, "entry": entry}


@app.post("/api/compliance/check")
async def compliance_check() -> dict[str, Any]:
    _require_product("compliance")
    ledger = AppendOnlyLedger(_compliance_db())
    ctx = build_compliance_context(ledger, run_f9=True)
    report = run_institutional_check(ledger=ledger, context=ctx, run_f9=False)
    return report.to_dict()


@app.post("/api/compliance/export")
async def compliance_export() -> dict[str, Any]:
    _require_product("compliance")
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
    _require_product("compliance")
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
    _require_product("proxy")
    ledger = AppendOnlyLedger(_proxy_db())
    entries = ledger.list_entries()
    proxy_rows = [e for e in entries if e.get("event_type") == "proxy_request"]
    return {"entries": entries, "proxy_rows": proxy_rows, "verify": ledger.verify()}


@app.post("/api/proxy/evaluate")
async def proxy_evaluate(body: ProxyEvaluateBody) -> dict[str, Any]:
    _require_product("proxy")
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
    _require_product("proxy")
    ledger = AppendOnlyLedger(_proxy_db())
    ctx = build_compliance_context(ledger, run_f9=True)
    report = run_institutional_check(ledger=ledger, context=ctx, run_f9=False)
    return report.to_dict()


@app.post("/api/proxy/export")
async def proxy_export() -> dict[str, Any]:
    _require_product("proxy")
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
    _require_product("proxy")
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
