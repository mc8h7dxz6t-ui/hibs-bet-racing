import pandas as pd

from hibs_racing.cards.actionability import value_gate_reason


def test_suitability_poor_distance():
    reason = value_gate_reason(
        {
            "race_name": "Class 4 Handicap",
            "official_rating": 60,
            "horse_distance_runs": 4,
            "horse_distance_wins": 0,
            "form_trip_change_f": 3.0,
        },
        {
            "suitability_gates_enabled": True,
            "min_horse_dist_runs": 3,
            "block_zero_dist_wins": True,
            "max_trip_change_f": 2.0,
            "exempt_unrated_races": True,
            "require_official_rating_for_value": True,
            "min_official_rating": 45,
        },
    )
    assert reason == "poor_distance_record"
