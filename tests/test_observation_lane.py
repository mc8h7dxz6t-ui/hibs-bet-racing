"""Observation lane — institutional check and telemetry behaviour."""

from __future__ import annotations

from hibs_racing.features.store import init_db
from hibs_racing.institutional.check import run_institutional_check
from hibs_racing.institutional.telemetry_balance import telemetry_balance_for_date


def test_observation_lane_skips_gate_regression(tmp_path):
    db = tmp_path / "obs.db"
    init_db(db)
    report = run_institutional_check(
        days=14,
        card_date="2026-06-05",
        observation_lane=True,
        database=db,
    )
    assert report.gate_regression.get("report_summary", {}).get("skipped") is True
    gate_checks = [c for c in report.checks if c["name"] == "gate_regression"]
    assert gate_checks and gate_checks[0]["passed"] is True


def test_observation_lane_passes_without_manifest(tmp_path):
    db = tmp_path / "obs2.db"
    init_db(db)
    report = run_institutional_check(
        days=1,
        card_date="2026-06-05",
        observation_lane=True,
        database=db,
    )
    tb = report.telemetry_balance or {}
    assert tb.get("passed") is True
    assert "pending" in (tb.get("message") or "").lower()


def test_observation_telemetry_pending_no_manifest(tmp_path):
    db = tmp_path / "obs3.db"
    init_db(db)
    tb = telemetry_balance_for_date("2026-06-05", observation_lane=True, database=db)
    assert tb.passed is True
    assert tb.observation_lane is True


def test_observation_lane_ignores_require_recon_clean(tmp_path):
    db = tmp_path / "obs4.db"
    init_db(db)
    report = run_institutional_check(
        days=14,
        card_date="2026-06-05",
        require_recon_clean=True,
        observation_lane=True,
        database=db,
    )
    recon = [c for c in report.checks if c["name"] == "paper_reconciliation"]
    assert recon and recon[0]["passed"] is True
