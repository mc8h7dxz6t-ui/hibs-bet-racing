import pandas as pd

from hibs_racing.backtest.gate_benchmark import _apply_gate_flags, _settle
from hibs_racing.backtest.gate_regression import run_gate_regression_check
from hibs_racing.backtest.snapshot_store import upsert_snapshots
from hibs_racing.features.store import init_db


def _synthetic_snapshot_frame() -> pd.DataFrame:
    rows = []
    for i in range(20):
        rows.append(
            {
                "card_date": "2026-05-01",
                "runner_id": f"r{i}",
                "race_id": f"race{i // 5}",
                "course": "York",
                "race_name": "Handicap",
                "field_size": 10,
                "official_rating": 70 + i,
                "win_decimal": 4.0 + i * 0.1,
                "place_fraction": 0.25,
                "places": 3,
                "model_score": 1.0 - i * 0.01,
                "model_win_prob": 0.15,
                "model_place_prob": 0.35,
                "combo_bayes_place": 0.28,
                "place_ev": 0.08,
                "ew_combined_ev": 0.1,
                "flag_raw": 1,
                "finish_pos": 1 if i % 4 == 0 else 5,
            }
        )
    return pd.DataFrame(rows)


def test_gate_regression_passes_on_synthetic_snapshots(tmp_path):
    db = tmp_path / "reg.db"
    init_db(db)
    frame = _synthetic_snapshot_frame()
    upsert_snapshots(db, "2026-05-01", frame.drop(columns=["card_date"]), finish_by_runner={})

    paper = {
        "min_place_ev": 0.05,
        "min_combo_bayes_place": 0.22,
        "value_gates_enabled": True,
        "exempt_unrated_races": True,
        "require_official_rating_for_value": True,
        "min_official_rating": 45,
        "suitability_gates_enabled": False,
        "gate2": {"enabled": False},
        "regression": {"min_card_days": 1, "min_gate1_roi_delta_pp": -100.0, "min_gate1_hit_rate_delta_pp": -100.0},
    }

    gated = _apply_gate_flags(frame, paper)
    none = _settle(gated, "flag_none")
    g1 = _settle(gated, "flag_gate1")
    assert none["picks"] > 0

    check = run_gate_regression_check(
        start="2026-05-01",
        end="2026-05-01",
        database=db,
        min_card_days=1,
    )
    assert check.report_summary.get("card_days") == 1
    assert "checks" in check.to_dict()
