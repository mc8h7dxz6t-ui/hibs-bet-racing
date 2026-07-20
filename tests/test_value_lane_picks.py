"""Tests for value-lane pick ranking."""

from __future__ import annotations

import pandas as pd

from hibs_racing.monitor import top_value_lane_picks


def test_top_value_lane_picks_ranks_by_ev_one_per_race():
    frame = pd.DataFrame(
        [
            {
                "race_id": "R1",
                "horse_name": "Alpha",
                "value_flag": 1,
                "ew_combined_ev": 0.15,
                "field_size": 8,
            },
            {
                "race_id": "R1",
                "horse_name": "Beta",
                "value_flag": 1,
                "ew_combined_ev": 0.05,
                "field_size": 8,
            },
            {
                "race_id": "R2",
                "horse_name": "Gamma",
                "value_flag": 1,
                "ew_combined_ev": 0.22,
                "field_size": 10,
            },
            {
                "race_id": "R3",
                "horse_name": "NoValue",
                "value_flag": 0,
                "ew_combined_ev": 0.99,
                "field_size": 9,
            },
        ]
    )
    picks = top_value_lane_picks(frame, top_n=4)
    names = [p["horse_name"] for p in picks]
    assert names == ["Gamma", "Alpha"]
    assert picks[0]["value_lane_rank"] == 1
    assert picks[1]["value_lane_rank"] == 2
