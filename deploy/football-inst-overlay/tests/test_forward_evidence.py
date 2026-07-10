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
    assert "since_deploy" in rep
    ids = {g["id"] for g in rep["gates"]}
    assert "F1_audit" in ids
    assert "F7_forward_capture_7d" in ids
    assert "F9_clv_beat_close" in ids
    assert "F9b_clv_beat_close_fair_shin" in ids
    assert "F9c_clv_benchmark_tier" in ids
    f9b = next(g for g in rep["gates"] if g["id"] == "F9b_clv_beat_close_fair_shin")
    assert f9b.get("informational") is True


def test_evidence_deploy_since_iso(monkeypatch):
    monkeypatch.setenv("HIBS_EVIDENCE_DEPLOY_DATE", "2026-06-10")
    from hibs_predictor.forward_evidence import deploy_revision_iso, evidence_deploy_since_iso

    assert evidence_deploy_since_iso() == "2026-06-10T00:00:00+00:00"
    assert deploy_revision_iso() == "2026-06-10T00:00:00+00:00"


def test_ensure_audit_db_and_log_helpers(monkeypatch, tmp_path):
    monkeypatch.setenv("HIBS_PREDICTION_LOG_ENABLED", "0")
    from hibs_predictor.forward_evidence import ensure_audit_db, log_forward_snapshots_from_bundle, run_daily_clv_sync

    ensure_audit_db()
    assert log_forward_snapshots_from_bundle() == 0
    sync = run_daily_clv_sync()
    assert sync.get("enabled") is False


def test_safe_forward_evidence_never_raises():
    from hibs_predictor.institutional_failsafe import safe_forward_evidence_gates

    rep = safe_forward_evidence_gates()
    assert "gates" in rep or "error" in rep
