"""Tests for racing DQ-max persistence."""

from __future__ import annotations

import pandas as pd

from hibs_racing.cards.dq_persist import merge_runners_preserve_best, mean_runner_dq


def test_merge_runners_preserves_higher_dq():
    existing = pd.DataFrame(
        [
            {
                "runner_id": "r1",
                "horse_name": "Alpha",
                "win_decimal": 3.5,
                "official_rating": 110,
                "form_string": "112",
            }
        ]
    )
    incoming = pd.DataFrame(
        [
            {
                "runner_id": "r1",
                "horse_name": "Alpha",
                "win_decimal": None,
                "official_rating": 90,
                "form_string": None,
            }
        ]
    )
    merged = merge_runners_preserve_best(existing, incoming)
    row = merged.iloc[0].to_dict()
    assert row["official_rating"] == 110
    assert row["win_decimal"] == 3.5


def test_merge_runners_keeps_existing_not_in_incoming():
    existing = pd.DataFrame(
        [
            {"runner_id": "r1", "horse_name": "A", "win_decimal": 4.0},
            {"runner_id": "r2", "horse_name": "B", "win_decimal": 5.0},
        ]
    )
    incoming = pd.DataFrame([{"runner_id": "r1", "horse_name": "A", "win_decimal": 3.0}])
    merged = merge_runners_preserve_best(existing, incoming)
    assert len(merged) == 2
    assert mean_runner_dq(merged) >= mean_runner_dq(existing)
