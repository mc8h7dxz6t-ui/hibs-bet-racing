import pandas as pd

from hibs_racing.backtest.snapshot_store import scoring_config_hash
from hibs_racing.cards.actionability import apply_value_gates, value_gate_reason
from hibs_racing.cards.data_quality import runner_data_quality_pct
from hibs_racing.cards.engine_profile import build_engine_profile
from hibs_racing.cards.harville_config import harville_longshot_discount, harville_runtime_config


def test_runner_data_quality_maiden_exempt():
    pct = runner_data_quality_pct(
        {
            "race_name": "Maiden Stakes",
            "win_decimal": 5.0,
            "model_win_prob": 0.1,
            "model_place_prob": 0.3,
            "jockey": "A",
            "trainer": "B",
        }
    )
    assert pct == 100


def test_value_gate_below_data_quality():
    reason = value_gate_reason(
        {
            "race_name": "Class 4 Handicap",
            "official_rating": 70,
            "jockey": "A",
        },
        {"min_data_quality_pct": 75, "exempt_unrated_races": True, "enforce_steam_gate": False},
    )
    assert reason == "below_data_quality"


def test_value_gate_steam_abort():
    reason = value_gate_reason(
        {
            "race_name": "Class 4 Handicap",
            "official_rating": 70,
            "win_decimal": 5.0,
            "model_win_prob": 0.1,
            "model_place_prob": 0.3,
            "jockey": "A",
            "trainer": "B",
            "card_comment": "held up",
            "steam_gate": "abort",
        },
        {
            "min_data_quality_pct": 75,
            "enforce_steam_gate": True,
            "allowed_steam_gates": ["proceed", "scale_up", "unknown"],
        },
    )
    assert reason == "steam_gate_abort"


def test_apply_value_gates_steam_unknown_allowed():
    frame = pd.DataFrame(
        [
            {
                "value_flag": 1,
                "race_name": "Class 4 Handicap",
                "official_rating": 70,
                "win_decimal": 5.0,
                "model_win_prob": 0.1,
                "model_place_prob": 0.3,
                "jockey": "A",
                "trainer": "B",
                "card_comment": "held up",
                "runner_id": "r1",
                "steam_gate": "unknown",
            }
        ]
    )
    out = apply_value_gates(
        frame,
        {
            "min_data_quality_pct": 75,
            "enforce_steam_gate": True,
            "allowed_steam_gates": ["proceed", "scale_up", "unknown"],
        },
    )
    assert int(out.iloc[0]["value_flag"]) == 1
    assert "data_quality_pct" in out.columns


def test_config_hash_includes_harville_env(monkeypatch):
    monkeypatch.setenv("HIBS_HARVILLE_CORRECTION", "1")
    h1 = scoring_config_hash({"min_place_ev": 0.05, "harville_longshot_discount": 0.85})
    monkeypatch.delenv("HIBS_HARVILLE_CORRECTION", raising=False)
    h2 = scoring_config_hash({"min_place_ev": 0.05, "harville_longshot_discount": 0.85})
    assert h1 != h2


def test_harville_correction_env():
    assert harville_longshot_discount(0.85) == 0.85
    hv = harville_runtime_config()
    assert "effective_discount" in hv
    assert "correction_env" in hv


def test_build_engine_profile_shape():
    profile = build_engine_profile()
    assert profile["ranker_tier"] in ("base_36", "enrich_48")
    assert "harville" in profile
    assert "ranker_feature_manifest" in profile
