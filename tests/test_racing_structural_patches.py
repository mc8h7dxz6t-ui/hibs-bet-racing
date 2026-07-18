"""Racing evidence HTTP surface and execution env gates."""

from __future__ import annotations

import json

from hibs_racing.evidence_gates import PLACE_BRIER_PASS_MAX, racing_evidence_gates_from_health
from hibs_racing.live.execution_config import (
    execution_disabled,
    live_routing_allowed,
    live_routing_confirmed,
)
from hibs_racing.web import create_app


def test_place_brier_pass_max_exported():
    assert PLACE_BRIER_PASS_MAX == 0.25


def test_api_evidence_route():
    app = create_app()
    client = app.test_client()
    resp = client.get("/api/evidence")
    assert resp.status_code == 200
    body = resp.get_json()
    assert "gates" in body
    assert any(g["id"].startswith("R") for g in body["gates"])
    assert body.get("source") == "local_health"


def test_execution_env_gates_default_analytics(monkeypatch):
    monkeypatch.delenv("HIBS_RACING_LIVE_ROUTING_ALLOWED", raising=False)
    monkeypatch.delenv("HIBS_RACING_CONFIRM_LIVE", raising=False)
    assert live_routing_allowed() is False
    assert live_routing_confirmed() is False
    assert execution_disabled() is True


def test_execution_env_gates_armed_when_dual_confirm(monkeypatch):
    monkeypatch.setenv("HIBS_RACING_LIVE_ROUTING_ALLOWED", "1")
    monkeypatch.setenv("HIBS_RACING_CONFIRM_LIVE", "YES")
    assert live_routing_allowed() is True
    assert live_routing_confirmed() is True
    assert execution_disabled() is False


def test_racing_evidence_gates_from_health_shape():
    health = {
        "db_ok": True,
        "card_fresh": True,
        "nan_integrity_passed": True,
        "data_producer": {"ok": True},
        "telemetry_balance": {"coverage_pct": 55.0},
        "paper_recon_clean": True,
        "paper": {"n_rows": 40, "settled": 30},
        "place_reliability": {"brier": 0.22, "n": 30},
    }
    rep = racing_evidence_gates_from_health(health)
    assert json.dumps(rep)  # serializable
    assert len(rep["gates"]) == 8
