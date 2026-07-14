"""Workflow UI — FastAPI routes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def workflow_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    product = getattr(request, "param", "both")
    compliance_db = tmp_path / "compliance.sqlite"
    proxy_db = tmp_path / "proxy.sqlite"
    export_dir = tmp_path / "exports"

    monkeypatch.setenv("INST_COMPLIANCE_DB", str(compliance_db))
    monkeypatch.setenv("INST_PROXY_DB", str(proxy_db))
    monkeypatch.setenv("INST_EXPORT_DIR", str(export_dir))
    monkeypatch.setenv("INST_PROXY_SHADOW", "1")
    monkeypatch.setenv("INST_WORKFLOW_PRODUCT", product)

    import inst_workflow.serve as serve_mod

    serve_mod.state.compliance_db = compliance_db
    serve_mod.state.proxy_db = proxy_db
    serve_mod.state.export_dir = export_dir
    serve_mod.state.demo_dir = export_dir.parent / "portfolio"
    serve_mod.state.proxy_shadow = True
    serve_mod.state.product = product
    serve_mod.reset_proxy_runtime()

    with TestClient(serve_mod.app) as client:
        yield client, serve_mod, compliance_db, proxy_db, export_dir, product


def test_health(workflow_client):
    client, *_ = workflow_client
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert "compliance-logger" in body["products"]


def test_index_serves_html(workflow_client):
    client, *_ = workflow_client
    r = client.get("/")
    assert r.status_code == 200
    assert "Workflow Console" in r.text


def test_static_assets(workflow_client):
    client, *_ = workflow_client
    for path in ("/static/workflow.css", "/static/workflow.js"):
        r = client.get(path)
        assert r.status_code == 200
        assert len(r.content) > 100


def test_compliance_workflow(workflow_client):
    client, _, compliance_db, _, export_dir, _ = workflow_client
    snap_path = Path("docs/demo_snapshot.json")
    snapshot = json.loads(snap_path.read_text(encoding="utf-8"))

    r = client.post(
        "/api/compliance/ingest",
        json={"snapshot": snapshot, "outcome": {"status": "approved"}},
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert compliance_db.is_file()

    r = client.get("/api/compliance/ledger")
    assert r.status_code == 200
    assert r.json()["count"] >= 1

    r = client.post("/api/compliance/check")
    assert r.status_code == 200
    report = r.json()
    assert "checks" in report
    assert any(c["name"] == "F3" for c in report["checks"])

    r = client.post("/api/compliance/export")
    assert r.status_code == 200
    assert r.json()["product"] == "compliance-logger"
    assert (export_dir / "compliance_bundle.tar").is_file()

    r = client.post("/api/compliance/verify-bundle")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_proxy_evaluate_shadow(workflow_client):
    client, _, _, proxy_db, _, _ = workflow_client
    req = {
        "client_id": "ui-test",
        "method": "POST",
        "path": "/orders",
        "body": {"qty": 1},
        "idempotency_key": "wf-test-1",
        "live": False,
    }
    r = client.post("/api/proxy/evaluate", json=req)
    assert r.status_code == 200
    body = r.json()
    assert body["decision"].upper() in {"APPROVE", "REJECT", "KILL"}
    assert proxy_db.is_file()

    r = client.get("/api/proxy/ledger")
    assert r.status_code == 200
    assert len(r.json()["entries"]) >= 1


def test_demo_loaders(workflow_client):
    client, *_ = workflow_client
    assert client.get("/api/demo/compliance-snapshot").status_code == 200
    assert client.get("/api/demo/proxy-request").status_code == 200


def test_workflow_config(workflow_client):
    client, *_ = workflow_client
    r = client.get("/api/config")
    assert r.status_code == 200
    body = r.json()
    assert body["product"] == "both"
    assert body["tabs"]["arch"] is True
    assert body["tabs"]["compliance"] is True
    assert body["tabs"]["proxy"] is True


@pytest.mark.parametrize("workflow_client", ["compliance"], indirect=True)
def test_compliance_only_product(workflow_client):
    client, *_ = workflow_client
    cfg = client.get("/api/config").json()
    assert cfg["product"] == "compliance"
    assert cfg["tabs"]["proxy"] is False
    assert cfg["default_tab"] == "compliance"
    assert client.post("/api/proxy/evaluate", json={"client_id": "x"}).status_code == 404


@pytest.mark.parametrize("workflow_client", ["proxy"], indirect=True)
def test_proxy_only_product(workflow_client):
    client, *_ = workflow_client
    cfg = client.get("/api/config").json()
    assert cfg["product"] == "proxy"
    assert cfg["tabs"]["compliance"] is False
    assert cfg["default_tab"] == "proxy"
    assert client.post("/api/compliance/ingest", json={"snapshot": {}}).status_code == 404


def test_proof_catalog_and_spine_workflow(workflow_client, tmp_path: Path):
    client, serve_mod, _, _, export_dir, _ = workflow_client
    demo_dir = tmp_path / "portfolio"
    demo_dir.mkdir()
    serve_mod.state.demo_dir = demo_dir

    # Seed alt-data ledger via CLI pattern
    alt_db = demo_dir / "altdata.sqlite"
    from altdata.cli import main as alt_main

    alt_main(
        [
            "poll",
            "--feed",
            "demo_feed",
            "--ctx",
            '{"demo_price":1,"demo_seats":1,"route_code":"X","raw_html":"<td>1</td>"}',
            "--database",
            str(alt_db),
        ]
    )

    r = client.get("/api/products")
    assert r.status_code == 200
    catalog = r.json()["catalog"]
    assert len(catalog) == 12

    r = client.post("/api/proof/select", json={"product_id": "altdata"})
    assert r.status_code == 200

    r = client.get("/api/proof/altdata/ledger")
    assert r.status_code == 200
    assert r.json()["count"] >= 1

    r = client.post("/api/proof/altdata/check")
    assert r.status_code == 200
    assert "checks" in r.json()

    r = client.post("/api/proof/altdata/export")
    assert r.status_code == 200
    assert (export_dir / "altdata_bundle.tar").is_file()

    r = client.post("/api/proof/altdata/verify-bundle")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_workflow_config_includes_proof_tab(workflow_client):
    client, *_ = workflow_client
    cfg = client.get("/api/config").json()
    assert cfg["tabs"]["proof"] is True
    assert len(cfg["proof"]["catalog"]) == 12


def test_ready_not_seeded(workflow_client):
    client, serve_mod, *_ = workflow_client
    demo_dir = serve_mod.state.demo_dir
    serve_mod.state.demo_dir = demo_dir.parent / "empty_portfolio"
    serve_mod.state.demo_dir.mkdir(parents=True, exist_ok=True)

    r = client.get("/ready")
    assert r.status_code == 503
    body = r.json()
    assert body["ok"] is False
    assert body["ready"] is False
    assert body["checks"]["portfolio_seeded"]["ok"] is False
    assert "0/12" in body["checks"]["portfolio_seeded"]["detail"]


def test_health_portfolio_seeded_count(workflow_client):
    client, serve_mod, *_ = workflow_client
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["portfolio_total"] == 12
    assert "portfolio_seeded" in body
    assert body["portfolio_seeded"] <= 12


def test_proof_bootstrap_compliance(workflow_client):
    client, serve_mod, _, _, _, _ = workflow_client
    demo_dir = serve_mod.state.demo_dir
    demo_dir.mkdir(parents=True, exist_ok=True)
    compliance_db = demo_dir / "compliance.sqlite"

    r = client.get("/ready")
    assert r.json()["portfolio_seeded"] < 12

    r = client.post("/api/proof/compliance/bootstrap")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["product_id"] == "compliance"
    assert compliance_db.is_file()

    r = client.get("/ready")
    seeded = r.json()["portfolio_seeded"]
    assert seeded >= 1


def test_proof_bootstrap_all_endpoint_shape(workflow_client, monkeypatch):
    client, serve_mod, *_ = workflow_client
    demo_dir = serve_mod.state.demo_dir
    demo_dir.mkdir(parents=True, exist_ok=True)

    from inst_workflow import serve as serve_module
    from inst_workflow.catalog import PRODUCT_CATALOG

    def _fake_bootstrap_all(*, demo_dir, skip_live=True):
        return [
            {"ok": True, "product_id": e.id, "sku": e.sku}
            for e in PRODUCT_CATALOG
        ]

    monkeypatch.setattr(serve_module, "bootstrap_all", _fake_bootstrap_all)

    r = client.post("/api/proof/bootstrap-all")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["seeded"] == 12
    assert body["total"] == 12
    assert len(body["results"]) == 12


def test_proof_verify_all_missing_tarballs(workflow_client):
    client, serve_mod, *_ = workflow_client
    serve_mod.state.demo_dir = serve_mod.state.demo_dir.parent / "no_bundles"
    serve_mod.state.demo_dir.mkdir(parents=True, exist_ok=True)

    r = client.post("/api/proof/verify-all")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert body["verified_ok"] == 0
    assert body["total"] == 12


@pytest.mark.parametrize("workflow_client", ["both"], indirect=True)
def test_default_tab_proof_env(workflow_client, monkeypatch):
    monkeypatch.setenv("INST_WORKFLOW_DEFAULT_TAB", "proof")
    client, serve_mod, *_ = workflow_client
    serve_mod.state.default_tab = "proof"
    cfg = client.get("/api/config").json()
    assert cfg["default_tab"] == "proof"
