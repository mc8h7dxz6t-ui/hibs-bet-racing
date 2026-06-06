import pandas as pd

from hibs_racing.backtest.gate_impact import (
    _simulate_allow_reason,
    apply_experimental_lanes,
    evaluate_lane_promotion,
    gate3_config,
    gate4_config,
    gate5_config,
    gate6_config,
    gate7_config,
    marginal_reason_study,
)
from hibs_racing.backtest.gate_benchmark import _settle


def _sample_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "runner_id": "a",
                "race_id": "r1",
                "card_date": "2026-01-01",
                "course": "Ascot",
                "finish_pos": 1,
                "win_decimal": 5.0,
                "place_fraction": 0.25,
                "places": 3,
                "flag_none": 1,
                "flag_gate2": 1,
                "gate2_reason": None,
            },
            {
                "runner_id": "b",
                "race_id": "r1",
                "card_date": "2026-01-01",
                "course": "Ascot",
                "finish_pos": 4,
                "win_decimal": 8.0,
                "place_fraction": 0.25,
                "places": 3,
                "flag_none": 1,
                "flag_gate2": 0,
                "gate2_reason": "gate2_race_cap",
            },
            {
                "runner_id": "c",
                "race_id": "r2",
                "card_date": "2026-01-01",
                "course": "Ayr",
                "finish_pos": 8,
                "win_decimal": 12.0,
                "place_fraction": 0.25,
                "places": 3,
                "flag_none": 1,
                "flag_gate2": 0,
                "gate2_reason": "gate2_price_fragile",
            },
        ]
    )


def test_marginal_reason_study_re_admits_single_reason():
    frame = _sample_frame()
    baseline, rows = marginal_reason_study(frame)
    assert int(baseline["picks"]) == 1
    cap = next(r for r in rows if r.reason == "gate2_race_cap")
    assert cap.added_picks == 1
    assert cap.simulated_picks == 2


def test_simulate_allow_reason_keeps_baseline():
    frame = _sample_frame()
    sim = _simulate_allow_reason(
        frame,
        baseline_col="flag_gate2",
        reason_col="gate2_reason",
        raw_col="flag_none",
        reason="gate2_race_cap",
        sim_col="sim",
    )
    assert int(sim.loc[sim["runner_id"] == "a", "sim"].iloc[0]) == 1
    assert int(sim.loc[sim["runner_id"] == "b", "sim"].iloc[0]) == 1
    assert int(sim.loc[sim["runner_id"] == "c", "sim"].iloc[0]) == 0


def test_gate5_gate6_config_from_yaml():
    paper = {"min_official_rating": 45, "gate2": {"enabled": True, "max_value_per_race": 3, "max_value_per_meeting": 6}}
    full = {
        "paper": paper,
        "experimental_replay_lanes": {
            "gate5_sniper": {"min_official_rating": 60, "gate2": {"max_value_per_race": 1}},
            "gate6_market_bounded": {"gate2": {"min_win_decimal": 2.0, "max_win_decimal": 10.0}},
        },
    }
    g5 = gate5_config(paper, full)
    g6 = gate6_config(paper, full)
    assert g5["min_official_rating"] >= 60
    assert g6["gate2"]["min_win_decimal"] == 2.0
    assert g6["gate2"]["max_win_decimal"] == 10.0


def test_gate7_stricter_than_gate5():
    paper = {"min_official_rating": 45, "gate2": {"enabled": True}}
    full = {"paper": paper, "experimental_replay_lanes": {}}
    g5 = gate5_config(paper, full)
    g7 = gate7_config(paper, full)
    assert g7["min_official_rating"] >= g5["min_official_rating"]
    assert g7["gate2"]["max_value_per_meeting"] <= g5["gate2"]["max_value_per_meeting"]


def test_gate2_price_band_reason():
    from hibs_racing.cards.actionability import value_gate_reason

    reason = value_gate_reason(
        {
            "race_name": "Class 4 Handicap",
            "official_rating": 60,
            "win_decimal": 15.0,
            "field_size": 10,
            "place_ev": 0.08,
            "combo_bayes_place": 0.30,
            "model_place_prob": 0.35,
            "ew_combined_ev": 0.10,
            "trainer_rtf": 12,
        },
        {
            "value_gates_enabled": True,
            "gate2": {"enabled": True, "min_win_decimal": 2.0, "max_win_decimal": 10.0, "min_confidence": 0.55},
        },
    )
    assert reason == "gate2_price_band"


def test_promotion_evaluation_volume_floor():
    full = {
        "experimental_replay_lanes": {
            "promotion_criteria": {"min_picks_per_month_gate5": 15, "min_aggregate_roi_pct": 10.0},
        }
    }
    promo = evaluate_lane_promotion(
        aggregate={
            "gate3": {"picks": 80, "roi_pct": 8.0},
            "gate5": {"picks": 40, "roi_pct": 12.0},
            "gate6": {"picks": 200, "roi_pct": 8.0},
            "gate7": {"picks": 10, "roi_pct": 12.0},
            "gate8": {"picks": 200, "roi_pct": 8.0},
        },
        period_rows=[{"gate2": {"picks": 100, "roi_pct": 5.0}, "gate5": {"picks": 5, "roi_pct": 12.0}, "gate3": {"picks": 80, "roi_pct": 8.0}}] * 8,
        months_with_data=8,
        full_cfg=full,
    )
    assert promo["gate5"]["avg_picks_per_dense_month"] == 5.0
    assert promo["gate5"]["volume_floor_pass"] is False
    assert promo["gate5"]["promotion_ready"] is False



def test_gate3_tighter_than_gate4_config():
    paper = {"min_official_rating": 45, "gate2": {"enabled": True, "max_value_per_race": 3, "max_value_per_meeting": 6}}
    g3 = gate3_config(paper)
    g4 = gate4_config(paper)
    assert g3["min_official_rating"] >= 50
    assert g3["gate2"]["max_value_per_race"] <= g4["gate2"]["max_value_per_race"]


def test_apply_experimental_lanes_includes_gate5_gate6():
    paper = {
        "value_gates_enabled": True,
        "exempt_unrated_races": True,
        "require_official_rating_for_value": True,
        "min_official_rating": 45,
        "gate2": {"enabled": True, "max_value_per_race": 3, "max_value_per_meeting": 6},
    }
    frame = pd.DataFrame(
        [
            {
                "runner_id": "x",
                "race_id": "r1",
                "card_date": "2026-01-01",
                "course": "Ascot",
                "race_name": "Class 4 Handicap",
                "official_rating": 60,
                "field_size": 10,
                "finish_pos": 2,
                "win_decimal": 6.0,
                "place_fraction": 0.25,
                "places": 3,
                "place_ev": 0.08,
                "combo_bayes_place": 0.30,
                "model_place_prob": 0.35,
                "ew_combined_ev": 0.10,
                "flag_raw": 1,
            }
        ]
    )
    frame["flag_none"] = 1
    out = apply_experimental_lanes(frame, paper)
    assert "flag_gate7" in out.columns
    assert "flag_gate8" in out.columns
