"""Industry-standard audit fixes — evidence truth, R8 Brier, Gate3 lane, calibration."""

from __future__ import annotations

import json

import pandas as pd

from hibs_racing.analytics.evidence_truth_plane import build_evidence_truth_plane
from hibs_racing.cards.lane_paper import attach_lane_flags, gate3_lane_config_summary
from hibs_racing.daily.smart_picks import _digest_hash, filter_smart_picks
from hibs_racing.evidence_gates import PLACE_BRIER_PASS_MAX, racing_evidence_gates_from_health
from hibs_racing.models.win_prob_calibration import _apply_knots, apply_win_prob_calibration


def test_evidence_truth_plane_includes_benchmark_planes():
    out = build_evidence_truth_plane(health={}, days=90)
    ids = {p["id"] for p in out["planes"]}
    assert "forward_offered" in ids or "forward_sp" in ids
    assert out.get("reconciliation_note")


def test_r8_place_brier_gate_pass():
    health = {
        "db_ok": True,
        "card_fresh": True,
        "nan_integrity_passed": True,
        "data_producer": {"ok": True},
        "telemetry_balance": {"coverage_pct": 55.0},
        "paper_recon_clean": True,
        "paper": {"n_rows": 40},
        "place_reliability": {"brier": 0.22, "n": 30},
    }
    rep = racing_evidence_gates_from_health(health)
    r8 = next(g for g in rep["gates"] if g["id"] == "R8_place_brier")
    assert r8["pass"] is True
    assert r8["actual"] <= PLACE_BRIER_PASS_MAX


def test_r8_insufficient_sample_fails():
    health = {
        "db_ok": True,
        "card_fresh": True,
        "nan_integrity_passed": True,
        "data_producer": {"ok": True},
        "telemetry_balance": {"coverage_pct": 55.0},
        "paper_recon_clean": True,
        "paper": {"n_rows": 40},
        "place_reliability": {"brier": 0.18, "n": 5},
    }
    rep = racing_evidence_gates_from_health(health)
    r8 = next(g for g in rep["gates"] if g["id"] == "R8_place_brier")
    assert r8["pass"] is False
    assert r8.get("insufficient_sample") is True


def test_win_prob_calibration_renormalizes_per_race(monkeypatch, tmp_path):
    knots = [{"x": 0.1, "y": 0.08}, {"x": 0.5, "y": 0.45}, {"x": 0.9, "y": 0.85}]
    cache = tmp_path / "win_prob_isotonic.json"
    cache.write_text(json.dumps({"knots": knots}), encoding="utf-8")
    import hibs_racing.models.win_prob_calibration as wpc

    monkeypatch.setattr(wpc, "calibration_cache_path", lambda: cache)
    monkeypatch.setattr(wpc, "calibration_enabled", lambda: True)
    frame = pd.DataFrame(
        {
            "race_id": ["r1", "r1", "r2", "r2"],
            "model_win_prob": [0.5, 0.3, 0.4, 0.4],
        }
    )
    out = wpc.apply_win_prob_calibration(frame)
    for rid in out["race_id"].unique():
        s = float(out.loc[out["race_id"] == rid, "model_win_prob"].sum())
        assert 0.99 <= s <= 1.01


def test_apply_knots_monotonic():
    knots = [{"x": 0.2, "y": 0.15}, {"x": 0.8, "y": 0.7}]
    assert _apply_knots(0.5, knots) > _apply_knots(0.2, knots)


def test_smart_picks_gate3_filter(monkeypatch):
    monkeypatch.setattr(
        "hibs_racing.daily.smart_picks._smart_picks_lane",
        lambda: "gate3",
    )
    candidates = [
        {
            "value_flag": 1,
            "value_gate_reason": "",
            "data_quality_pct": 96,
            "steam_gate": "proceed",
            "flag_gate3": 1,
            "place_score": 0.4,
        },
        {
            "value_flag": 1,
            "value_gate_reason": "",
            "data_quality_pct": 96,
            "steam_gate": "proceed",
            "flag_gate3": 0,
            "place_score": 0.9,
        },
    ]
    picks = filter_smart_picks(candidates, limit=3)
    assert len(picks) == 1
    assert picks[0]["place_score"] == 0.4


def test_smart_picks_digest_hash_stable():
    picks = [{"runner_id": "a", "horse_name": "A", "win_decimal": 3.0, "ew_combined_ev": 0.1}]
    h1 = _digest_hash(picks, config_hash="abc", lane="gate3")
    h2 = _digest_hash(picks, config_hash="abc", lane="gate3")
    assert h1 == h2


def test_attach_lane_flags_adds_gate3_column():
    frame = pd.DataFrame(
        {
            "race_id": ["r1"],
            "runner_id": ["x"],
            "value_flag": [0],
            "flag_raw": [0],
            "model_score": [1.0],
            "model_win_prob": [0.5],
            "model_place_prob": [0.3],
            "combo_bayes_place": [0.25],
            "place_ev": [0.0],
            "ew_combined_ev": [0.0],
            "official_rating": [55],
            "trainer_rtf": [20],
            "data_quality_pct": [95],
            "field_size": [10],
        }
    )
    out = attach_lane_flags(frame)
    assert "flag_gate3" in out.columns


def test_gate3_lane_config_summary():
    summary = gate3_lane_config_summary()
    assert summary["lane"] == "gate3"
    assert summary["min_confidence"] >= 0.6
