import pandas as pd

from hibs_racing.cards.actionability import apply_value_gates, value_gate_reason


def _cfg() -> dict:
    return {
        "value_gates_enabled": True,
        "exempt_unrated_races": True,
        "require_official_rating_for_value": False,
        "min_official_rating": 45,
        "enforce_steam_gate": False,
        "min_data_quality_pct": None,
        "gate2": {
            "enabled": True,
            "min_confidence": 0.6,
            "small_field_max": 7,
            "large_field_min": 12,
            "min_place_ev_small": 0.04,
            "min_place_ev_medium": 0.05,
            "min_place_ev_large": 0.07,
            "min_combo_small": 0.20,
            "min_combo_medium": 0.22,
            "min_combo_large": 0.25,
            "price_shock_per_decimal": 0.01,
            "min_stressed_place_ev": 0.0,
            "max_value_per_race": 1,
        },
    }


def test_gate2_low_confidence_reason():
    reason = value_gate_reason(
        {
            "race_name": "Class 4 Handicap",
            "field_size": 10,
            "place_ev": 0.2,
            "combo_bayes_place": 0.4,
            "win_decimal": 9.0,
            "official_rating": None,
            "trainer_rtf": None,
        },
        _cfg(),
    )
    assert reason == "gate2_low_confidence"


def test_gate2_regime_large_field_threshold():
    reason = value_gate_reason(
        {
            "race_name": "Class 4 Handicap",
            "field_size": 14,
            "official_rating": 72,
            "place_ev": 0.05,
            "combo_bayes_place": 0.30,
            "model_place_prob": 0.40,
            "ew_combined_ev": 0.1,
            "win_decimal": 7.0,
            "trainer_rtf": 15,
        },
        _cfg(),
    )
    assert reason == "gate2_regime_ev"


def test_gate2_race_cap_blocks_excess():
    frame = pd.DataFrame(
        [
            {
                "runner_id": "a",
                "race_id": "r1",
                "card_date": "2026-06-02",
                "course": "York",
                "value_flag": 1,
                "race_name": "Class 4 Handicap",
                "place_ev": 0.2,
                "combo_bayes_place": 0.4,
                "model_place_prob": 0.4,
                "ew_combined_ev": 0.15,
                "win_decimal": 5.0,
                "official_rating": 70,
                "trainer_rtf": 12,
                "field_size": 9,
            },
            {
                "runner_id": "b",
                "race_id": "r1",
                "card_date": "2026-06-02",
                "course": "York",
                "value_flag": 1,
                "race_name": "Class 4 Handicap",
                "place_ev": 0.2,
                "combo_bayes_place": 0.4,
                "model_place_prob": 0.4,
                "ew_combined_ev": 0.12,
                "win_decimal": 5.0,
                "official_rating": 70,
                "trainer_rtf": 12,
                "field_size": 9,
            },
        ]
    )
    out = apply_value_gates(frame, _cfg())
    assert int(out["value_flag"].sum()) == 1
    blocked = out[out["value_flag"] == 0]
    assert blocked["value_gate_reason"].iloc[0] == "gate2_race_cap"
