"""Forward evidence F1–F9 gate tests."""

from __future__ import annotations


def test_forward_evidence_gates_shape(monkeypatch):
    monkeypatch.setenv("HIBS_PREDICTION_LOG_ENABLED", "1")
    monkeypatch.setenv("HIBS_CLV_LOG_ENABLED", "1")
    monkeypatch.delenv("HIBS_PRODUCTION", raising=False)
    from hibs_predictor.forward_evidence import forward_evidence_gates

    rep = forward_evidence_gates()
    assert "gates" in rep
    assert "evidence_grade" in rep
    assert "buyer_ready" in rep
    assert "matchdays_7d" in rep
    ids = {g["id"] for g in rep["gates"]}
    assert "F1_prediction_log" in ids
    assert "F9_beat_close" in ids


def test_evidence_deploy_since_iso(monkeypatch):
    monkeypatch.setenv("HIBS_EVIDENCE_DEPLOY_DATE", "2026-06-10")
    from hibs_predictor.forward_evidence import evidence_deploy_since_iso

    assert evidence_deploy_since_iso() == "2026-06-10T00:00:00+00:00"


def test_safe_forward_evidence_never_raises():
    from hibs_predictor.institutional_failsafe import safe_forward_evidence_gates

    rep = safe_forward_evidence_gates()
    assert "gates" in rep or "error" in rep
