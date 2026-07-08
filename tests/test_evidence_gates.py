"""Racing evidence gates (R1–R7)."""

from __future__ import annotations

from hibs_racing.evidence_gates import racing_evidence_gates_from_health


def test_racing_evidence_gates_all_pass():
    health = {
        "db_ok": True,
        "card_fresh": True,
        "nan_integrity_passed": True,
        "data_producer": {"ok": True},
        "telemetry_balance": {"coverage_pct": 55.0},
        "paper_recon_clean": True,
        "paper": {"n_rows": 40, "settled": 30},
    }
    rep = racing_evidence_gates_from_health(health)
    assert rep["buyer_ready"] is True
    assert rep["evidence_grade"] == "A"


def test_racing_evidence_gates_paper_sample_fail():
    health = {
        "db_ok": True,
        "card_fresh": True,
        "nan_integrity_passed": True,
        "data_producer": {"ok": True},
        "telemetry_balance": {"coverage_pct": 55.0},
        "paper_recon_clean": True,
        "paper": {"n_rows": 5},
    }
    rep = racing_evidence_gates_from_health(health)
    assert rep["buyer_ready"] is False
    r7 = next(g for g in rep["gates"] if g["id"] == "R7_paper_sample")
    assert r7["pass"] is False
