import pandas as pd

from hibs_racing.cards.actionability import (
    apply_value_gates,
    attach_steam_gates,
    cap_place_prob,
    value_gate_reason,
)
from hibs_racing.cards.data_quality import is_exempt_unrated_race


def test_is_exempt_unrated_race():
    assert is_exempt_unrated_race({"race_name": "EBF Maiden Stakes"})
    assert is_exempt_unrated_race({"race_name": "Novices Limited Handicap Hurdle"})
    assert not is_exempt_unrated_race({"race_name": "Class 4 Handicap"})


def test_cap_place_prob_small_field():
    assert cap_place_prob(0.98, field_size=5) == 0.85
    assert cap_place_prob(0.80, field_size=5) == 0.80
    assert cap_place_prob(0.99, field_size=12) == 0.97


def test_value_gate_maiden_blocks_value():
    reason = value_gate_reason(
        {"race_name": "Maiden Stakes", "official_rating": None},
        {"exempt_unrated_races": True, "require_official_rating_for_value": True},
    )
    assert reason == "unrated_race_expected"


def test_value_gate_low_or():
    reason = value_gate_reason(
        {"race_name": "Class 5 Handicap", "official_rating": 40},
        {"min_official_rating": 45, "exempt_unrated_races": True},
    )
    assert reason == "below_or_floor"


def test_attach_steam_gates_handles_nan_value_flag(monkeypatch):
    def fake_steam_gate_by_runner(value_ids, cards=None):
        return {rid: "proceed" for rid in (value_ids or [])}

    monkeypatch.setattr(
        "hibs_racing.odds.market_steam.steam_gate_by_runner",
        fake_steam_gate_by_runner,
    )
    frame = pd.DataFrame(
        [
            {"runner_id": "r1", "value_flag": float("nan"), "race_id": "x"},
            {"runner_id": "r2", "value_flag": 1, "race_id": "x"},
        ]
    )
    out = attach_steam_gates(frame, {"enforce_steam_gate": True})
    assert "steam_gate" in out.columns
    assert len(out) == 2


def test_apply_value_gates_clears_flag():
    frame = pd.DataFrame(
        [
            {
                "value_flag": 1,
                "race_name": "Maiden Stakes",
                "official_rating": None,
                "model_place_prob": 0.9,
            },
            {
                "value_flag": 1,
                "race_name": "Class 4 Handicap",
                "official_rating": 70,
                "model_place_prob": 0.6,
            },
        ]
    )
    cfg = {
        "exempt_unrated_races": True,
        "require_official_rating_for_value": True,
        "min_official_rating": 45,
        "enforce_steam_gate": False,
        "min_data_quality_pct": None,
    }
    out = apply_value_gates(frame, cfg)
    assert int(out.iloc[0]["value_flag"]) == 0
    assert out.iloc[0]["value_gate_reason"] == "unrated_race_expected"
    assert int(out.iloc[1]["value_flag"]) == 1
    assert out.iloc[1]["value_gate_reason"] is None or pd.isna(out.iloc[1]["value_gate_reason"])
