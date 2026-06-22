"""Inst++ workflow UI — FastAPI routes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def workflow_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    compliance_db = tmp_path / "compliance.sqlite"
    proxy_db = tmp_path / "proxy.sqlite"
    export_dir = tmp_path / "exports"

    monkeypatch.setenv("INST_COMPLIANCE_DB", str(compliance_db))
    monkeypatch.setenv("INST_PROXY_DB", str(proxy_db))
    monkeypatch.setenv("INST_EXPORT_DIR", str(export_dir))
    monkeypatch.setenv("INST_PROXY_SHADOW", "1")

    import inst_workflow.serve as serve_mod

    serve_mod.state.compliance_db = compliance_db
    serve_mod.state.proxy_db = proxy_db
    serve_mod.state.export_dir = export_dir
    serve_mod.state.proxy_shadow = True
    serve_mod.reset_proxy_runtime()

    with TestClient(serve_mod.app) as client:
        yield client, serve_mod, compliance_db, proxy_db, export_dir


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
    assert "Inst++ Workflow Console" in r.text


def test_static_assets(workflow_client):
    client, *_ = workflow_client
    for path in ("/static/workflow.css", "/static/workflow.js"):
        r = client.get(path)
        assert r.status_code == 200
        assert len(r.content) > 100


def test_compliance_workflow(workflow_client):
    client, _, compliance_db, _, export_dir = workflow_client
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
    client, serve_mod, _, proxy_db, _ = workflow_client
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
