"""Tests for sniper lane (Gate7 overlay)."""

from __future__ import annotations

import pandas as pd

from hibs_racing.sniper_lane import passes_sniper_lane_row, top_sniper_lane_picks


def _row(**kwargs):
    base = {
        "race_id": "R1",
        "meeting_id": "M1",
        "horse_name": "Alpha",
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
        "steam_gate": "proceed",
        "data_quality_pct": 90,
    }
    base.update(kwargs)
    return base


def test_passes_sniper_lane_row_requires_gate7_thresholds():
    assert passes_sniper_lane_row(_row()) is True
    assert passes_sniper_lane_row(_row(official_rating=60)) is False
    assert passes_sniper_lane_row(_row(trainer_rtf=10)) is False
    assert passes_sniper_lane_row(_row(value_flag=0)) is False


def test_top_sniper_lane_picks_one_per_meeting_ranked_by_ev():
    frame = pd.DataFrame(
        [
            _row(race_id="R1", meeting_id="M1", horse_name="A", ew_combined_ev=0.20),
            _row(race_id="R2", meeting_id="M1", horse_name="B", ew_combined_ev=0.15),
            _row(race_id="R3", meeting_id="M2", horse_name="C", ew_combined_ev=0.25),
            _row(race_id="R4", meeting_id="M2", horse_name="Weak", official_rating=55, ew_combined_ev=0.99),
        ]
    )
    picks = top_sniper_lane_picks(frame, top_n=6)
    names = [p["horse_name"] for p in picks]
    assert names == ["C", "A"]
    assert picks[0]["sniper_lane_rank"] == 1
