"""Tests for racecard pick-quality gate classification."""

from __future__ import annotations

from hibs_racing.pick_quality import (
    attach_pick_quality_flags,
    classify_runner_pick_quality,
    normalize_gate_filter_mode,
    runner_passes_gate_filter,
)


def _runner(**kwargs):
    base = {
        "runner_id": "R1",
        "value_flag": 1,
        "value_gate_reason": None,
        "official_rating": 70,
        "trainer_rtf": 25.0,
        "field_size": 10,
        "model_place_prob": 0.55,
        "combo_bayes_place": 0.40,
        "place_ev": 0.12,
        "ew_combined_ev": 0.18,
        "win_decimal": 4.0,
        "market_gauge": {"gate": "proceed", "kelly_multiplier": 1.0},
    }
    base.update(kwargs)
    return base


def test_normalize_gate_filter_mode_rejects_unknown():
    assert normalize_gate_filter_mode("sniper") == "sniper"
    assert normalize_gate_filter_mode("bogus") == "all"
    assert normalize_gate_filter_mode(None) == "all"


def test_classify_runner_sniper_is_highest_tier():
    q = classify_runner_pick_quality(_runner())
    assert q["pick_gate_sniper"] is True
    assert q["pick_gate_value_lane"] is True
    assert q["pick_gate_tier"] == "sniper"


def test_classify_runner_paper_ready_when_dq_high(monkeypatch):
    row = _runner()
    monkeypatch.setattr(
        "hibs_racing.pick_quality.runner_data_quality_pct",
        lambda _r: 96,
    )
    monkeypatch.setattr(
        "hibs_racing.pick_quality.passes_gated_value_row",
        lambda _r, **_: True,
    )
    q = classify_runner_pick_quality(row)
    assert q["pick_gate_paper_ready"] is True


def test_classify_runner_low_or_not_sniper():
    q = classify_runner_pick_quality(_runner(official_rating=55))
    assert q["pick_gate_sniper"] is False
    assert q["pick_gate_tier"] != "sniper"


def test_runner_passes_gate_filter_modes():
    row = _runner()
    assert runner_passes_gate_filter(row, "all") is True
    assert runner_passes_gate_filter(row, "sniper") is True
    assert runner_passes_gate_filter(row, "value_lane") is True
    assert runner_passes_gate_filter(_runner(value_flag=0), "value") is False


def test_attach_pick_quality_flags_meetings():
    meetings = [
        {
            "races": [
                {
                    "runners": [_runner(runner_id="A"), _runner(runner_id="B", value_flag=0)],
                }
            ]
        }
    ]
    attach_pick_quality_flags(meetings)
    a = meetings[0]["races"][0]["runners"][0]
    b = meetings[0]["races"][0]["runners"][1]
    assert a["pick_gate_sniper"] is True
    assert b["pick_gate_value"] is False
