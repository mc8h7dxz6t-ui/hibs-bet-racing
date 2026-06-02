import pandas as pd

from hibs_racing.backtest.snapshot_store import (
    load_snapshots,
    scoring_config_hash,
    snapshot_coverage,
    upsert_snapshots,
)
from hibs_racing.features.store import init_db


def test_snapshot_roundtrip(tmp_path):
    db = tmp_path / "test.db"
    init_db(db)
    frame = pd.DataFrame(
        [
            {
                "runner_id": "r1",
                "race_id": "race1",
                "course": "Ascot",
                "race_name": "Handicap",
                "field_size": 10,
                "official_rating": 80,
                "win_decimal": 5.0,
                "place_fraction": 0.25,
                "places": 3,
                "model_score": 0.9,
                "model_win_prob": 0.2,
                "model_place_prob": 0.45,
                "combo_bayes_place": 0.3,
                "place_ev": 0.08,
                "ew_combined_ev": 0.1,
                "flag_raw": 1,
                "trainer_rtf": 12.0,
            }
        ]
    )
    n = upsert_snapshots(db, "2026-06-01", frame, finish_by_runner={"r1": 2})
    assert n == 1
    loaded = load_snapshots(db, "2026-06-01", "2026-06-01")
    assert len(loaded) == 1
    assert loaded.iloc[0]["runner_id"] == "r1"
    assert float(loaded.iloc[0]["trainer_rtf"]) == 12.0
    cov = snapshot_coverage(db, "2026-06-01", "2026-06-01", expected_dates=["2026-06-01"])
    assert cov["complete"] is True


def test_config_hash_stable():
    cfg = {"min_place_ev": 0.05, "gate2": {"enabled": False}}
    assert scoring_config_hash(cfg) == scoring_config_hash(cfg)
