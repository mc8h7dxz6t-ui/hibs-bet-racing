"""Proof Console guided ingest — API + programmatic ingest per SKU."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def proof_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    demo_dir = tmp_path / "portfolio"
    demo_dir.mkdir()
    export_dir = tmp_path / "exports"
    export_dir.mkdir()

    monkeypatch.setenv("PORTFOLIO_DEMO_DIR", str(demo_dir))
    monkeypatch.setenv("INST_EXPORT_DIR", str(export_dir))
    monkeypatch.setenv("INST_WORKFLOW_PRODUCT", "both")

    import inst_workflow.serve as serve_mod

    serve_mod.state.demo_dir = demo_dir
    serve_mod.state.export_dir = export_dir
    serve_mod.reset_proxy_runtime()

    with TestClient(serve_mod.app) as client:
        yield client, demo_dir, export_dir


@pytest.mark.parametrize(
    "product_id",
    [
        "altdata",
        "ai-kit",
        "webhook-mesh",
        "ad-guard",
        "health",
        "model-governor",
        "drift-gate",
        "webhook-replay",
        "spend-guard",
        "agent-ledger",
    ],
)
def test_proof_demo_payload_and_ingest(proof_client, product_id: str):
    client, demo_dir, _ = proof_client

    r = client.get(f"/api/proof/{product_id}/demo-payload")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["product_id"] == product_id
    assert isinstance(body["payload"], dict)

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

    db_name = {
        "altdata": "altdata.sqlite",
        "ai-kit": "ai_kit_trace.sqlite",
        "webhook-mesh": "webhook_mesh.sqlite",
        "ad-guard": "ad_guard.sqlite",
        "health": "health.sqlite",
        "model-governor": "model_governor.sqlite",
        "drift-gate": "drift_gate.sqlite",
        "webhook-replay": "webhook_replay.sqlite",
        "spend-guard": "spend_guard.sqlite",
        "agent-ledger": "agent_ledger.sqlite",
    }[product_id]
    assert (demo_dir / db_name).is_file()


def test_proof_ingest_not_available_for_compliance(proof_client):
    client, _, _ = proof_client
    assert client.get("/api/proof/compliance/demo-payload").status_code == 404
    assert client.post("/api/proof/compliance/ingest", json={"payload": {}}).status_code == 404


def test_proof_ingest_spine_after_ingest(proof_client):
    client, demo_dir, export_dir = proof_client
    payload_r = client.get("/api/proof/altdata/demo-payload")
    payload = payload_r.json()["payload"]
    client.post("/api/proof/altdata/ingest", json={"payload": payload})

    r = client.post("/api/proof/altdata/check")
    assert r.status_code == 200
    assert "checks" in r.json()

    r = client.post("/api/proof/altdata/export")
    assert r.status_code == 200
    assert (export_dir / "altdata_bundle.tar").is_file()

    r = client.post("/api/proof/altdata/verify-bundle")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_health_auto_seq_increments(proof_client):
    client, demo_dir, _ = proof_client
    base = client.get("/api/proof/health/demo-payload").json()["payload"]
    client.post("/api/proof/health/ingest", json={"payload": base})
    second = dict(base)
    client.post("/api/proof/health/ingest", json={"payload": second})
    ledger = client.get("/api/proof/health/ledger").json()
    assert ledger["count"] >= 2
