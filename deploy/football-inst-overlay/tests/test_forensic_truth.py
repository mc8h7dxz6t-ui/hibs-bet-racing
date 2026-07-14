"""Forensic truth alignment — code/math fixes from diligence audit."""

from __future__ import annotations


def test_truth_plane_win_brier_uses_brier_score():
    from hibs_racing.analytics.evidence_truth_plane import build_evidence_truth_plane

    out = build_evidence_truth_plane(
        health={"reliability": {"brier_score": 0.19, "n": 42}, "place_reliability": {"brier": 0.22, "n": 30}},
        days=90,
    )
    assert out["calibration"]["win_brier"] == 0.19
    assert out["calibration"]["win_n"] == 42


def test_score_gates_skips_informational():
    from hibs_predictor.evidence_presentation import score_gates

    gates = [
        {"id": "A", "pass": True, "critical": True},
        {"id": "B", "pass": False, "critical": False, "informational": True},
    ]
    assert score_gates(gates) == 100


def test_stack_truth_lists_fabricated_names():
    from hibs_predictor.stack_truth import stack_truth_summary

    st = stack_truth_summary()
    assert "CyberGovernor" in st["fabricated_names_not_in_repo"]
    assert st["database_reality"]["four_isolated_postgres_claim"] is False
    assert any(s["port"] == 5003 for s in st["services"])


def test_racing_overlay_includes_r8(monkeypatch):
    from hibs_predictor.racing_evidence import racing_evidence_gates_from_health

    health = {
        "telemetry_balance": {"coverage_pct": 55.0},
        "paper_recon_clean": True,
        "paper": {"settled": 30},
        "place_reliability": {"brier": 0.21, "n": 25},
    }
    rep = racing_evidence_gates_from_health(
        health,
        probes={},
        base_url="http://127.0.0.1:5003",
        health_ok=True,
        ping_ok=True,
        cards_ok=True,
        cards_nonempty=True,
    )
    ids = {g["id"] for g in rep["gates"]}
    assert "R8_place_brier" in ids
    r8 = next(g for g in rep["gates"] if g["id"] == "R8_place_brier")
    assert r8["pass"] is True
