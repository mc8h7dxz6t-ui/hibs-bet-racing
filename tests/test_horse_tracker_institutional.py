"""Institutional horse tracker: WfA, speed delta, horse_form_state."""

from __future__ import annotations

import pandas as pd

from hibs_racing.features.wfa import wfa_allowance_lbs


def test_wfa_allowance_summer_3yo():
    lbs = wfa_allowance_lbs(distance_f=6.0, age=3, race_date="2026-07-15")
    assert lbs >= 14


def test_speed_delta_stratified():
    from hibs_racing.features.speed_figure import compute_speed_deltas

    frame = pd.DataFrame(
        [
            {
                "course": "Ascot",
                "race_date": "2026-01-10",
                "race_type": "flat",
                "distance_f": 6.0,
                "race_class": "Class 3",
                "race_time_secs": 72.5,
                "weight_lbs": 130,
                "age": 4,
                "horse_id": "Horse A",
                "race_id": "r1",
                "finish_pos": 1,
            },
            {
                "course": "Ascot",
                "race_date": "2026-01-10",
                "race_type": "flat",
                "distance_f": 6.0,
                "race_class": "Class 3",
                "race_time_secs": 73.2,
                "weight_lbs": 128,
                "age": 5,
                "horse_id": "Horse B",
                "race_id": "r1",
                "finish_pos": 2,
            },
        ]
    )
    out = compute_speed_deltas(frame)
    assert "speed_figure_delta" in out.columns
    assert out["speed_figure_delta"].notna().any()


def test_horse_form_state_sigma_thin_sample():
    from hibs_racing.features.horse_form_state import sigma_from_runs

    assert sigma_from_runs(0) > sigma_from_runs(10)
