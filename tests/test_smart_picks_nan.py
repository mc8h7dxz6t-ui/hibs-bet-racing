import math

import pandas as pd

from hibs_racing.cards.ui_frame import gate_reason_is_clear, is_value_pick, normalize_gate_reason_for_db
from hibs_racing.daily.smart_picks import filter_smart_picks


def test_nan_gate_reason_is_clear_for_smart_portfolio():
    assert gate_reason_is_clear(float("nan"))
    assert gate_reason_is_clear(None)
    assert gate_reason_is_clear(pd.NA)
    assert not gate_reason_is_clear("missing_or")


def test_normalize_gate_reason_for_db_passing_value():
    assert normalize_gate_reason_for_db(float("nan")) is None
    assert normalize_gate_reason_for_db(None) is None
    assert normalize_gate_reason_for_db("missing_or") == "missing_or"


def test_filter_smart_picks_includes_value_with_nan_reason():
    candidates = [
        {
            "runner_id": "r1",
            "value_flag": 1,
            "value_gate_reason": float("nan"),
            "data_quality_pct": 80,
            "steam_gate": "unknown",
            "model_place_prob": 0.4,
        },
        {
            "runner_id": "r2",
            "value_flag": 1,
            "value_gate_reason": "missing_or",
            "data_quality_pct": 90,
            "steam_gate": "proceed",
            "model_place_prob": 0.5,
        },
    ]
    picks = filter_smart_picks(candidates, limit=3)
    assert len(picks) == 1
    assert picks[0]["runner_id"] == "r1"


def test_is_value_pick_rejects_nan_flag():
    assert not is_value_pick(float("nan"))
    assert is_value_pick(1)
