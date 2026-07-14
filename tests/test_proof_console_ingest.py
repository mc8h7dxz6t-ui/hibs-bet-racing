"""Proof Console guided ingest — API + programmatic ingest per SKU."""

from __future__ import annotations

import pytest


@pytest.fixture
def proof_client(tmp_path, monkeypatch: pytest.MonkeyPatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    demo_dir = tmp_path / "portfolio"
    demo_dir.mkdir()
    export_dir = tmp_path / "exports"
    export_dir.mkdir()
    compliance_db = demo_dir / "compliance.sqlite"
    proxy_db = demo_dir / "proxy.sqlite"

    monkeypatch.setenv("PORTFOLIO_DEMO_DIR", str(demo_dir))
    monkeypatch.setenv("INST_EXPORT_DIR", str(export_dir))
    monkeypatch.setenv("INST_WORKFLOW_PRODUCT", "both")
    monkeypatch.setenv("INST_COMPLIANCE_DB", str(compliance_db))
    monkeypatch.setenv("INST_PROXY_DB", str(proxy_db))

    import inst_workflow.serve as serve_mod

    serve_mod.state.demo_dir = demo_dir
    serve_mod.state.export_dir = export_dir
    serve_mod.state.compliance_db = compliance_db
    serve_mod.state.proxy_db = proxy_db
    serve_mod.reset_proxy_runtime()

    with TestClient(serve_mod.app) as client:
        yield client, demo_dir, export_dir, compliance_db, proxy_db


@pytest.mark.parametrize(
    "product_id,db_attr",
    [
        ("compliance", "compliance_db"),
        ("proxy", "proxy_db"),
        ("altdata", "altdata.sqlite"),
        ("ai-kit", "ai_kit_trace.sqlite"),
        ("webhook-mesh", "webhook_mesh.sqlite"),
        ("ad-guard", "ad_guard.sqlite"),
        ("health", "health.sqlite"),
        ("model-governor", "model_governor.sqlite"),
        ("drift-gate", "drift_gate.sqlite"),
        ("webhook-replay", "webhook_replay.sqlite"),
        ("spend-guard", "spend_guard.sqlite"),
        ("agent-ledger", "agent_ledger.sqlite"),
    ],
)
def test_proof_demo_payload_and_ingest(proof_client, product_id: str, db_attr: str):
    client, demo_dir, _, compliance_db, proxy_db = proof_client

    r = client.get(f"/api/proof/{product_id}/demo-payload")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["product_id"] == product_id
    assert isinstance(body["payload"], dict)
    assert body["schema"]["guided"] is True

    r = client.post(
        f"/api/proof/{product_id}/ingest",
        json={"payload": body["payload"]},
    )
    assert r.status_code == 200, r.text
    ingest = r.json()
    assert ingest.get("ok") is not False

    r = client.get(f"/api/proof/{product_id}/ledger")
    assert r.status_code == 200
    assert r.json()["count"] >= 1

    if db_attr == "compliance_db":
        assert compliance_db.is_file()
    elif db_attr == "proxy_db":
        assert proxy_db.is_file()
    else:
        assert (demo_dir / db_attr).is_file()


def test_proof_ingest_spine_after_ingest(proof_client):
    client, _, export_dir, *_ = proof_client
    payload = client.get("/api/proof/compliance/demo-payload").json()["payload"]
    client.post("/api/proof/compliance/ingest", json={"payload": payload})

    r = client.post("/api/proof/compliance/check")
    assert r.status_code == 200
    assert "checks" in r.json()

    r = client.post("/api/proof/compliance/export")
    assert r.status_code == 200
    assert (export_dir / "compliance_bundle.tar").is_file()

    r = client.post("/api/proof/compliance/verify-bundle")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_health_auto_seq_increments(proof_client):
    client, *_ = proof_client
    base = client.get("/api/proof/health/demo-payload").json()["payload"]
    client.post("/api/proof/health/ingest", json={"payload": base})
    client.post("/api/proof/health/ingest", json={"payload": dict(base)})
    ledger = client.get("/api/proof/health/ledger").json()
    assert ledger["count"] >= 2
