"""Wave 2 racing ranker tracker integration tests."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pandas as pd

from hibs_racing.features.horse_form_state import (
    HORSE_TRACKER_RANKER_FEATURES,
    attach_horse_tracker_features,
    impute_horse_tracker_features,
    upsert_horse_state,
)
from hibs_racing.features.ranker_matrix import (
    EXPECTED_TRACKER_FEATURE_COUNT,
    ranker_tracker_feature_columns,
)


def test_impute_enrich_fills_trainer_strike_from_rp_rate():
    from hibs_racing.features.ranker_matrix import impute_enrich_features

    frame = pd.DataFrame(
        {
            "form_string": [""],
            "trainer_rp_14d_win_rate": [0.22],
            "trainer_14d_strike": [None],
        }
    )
    out = impute_enrich_features(frame, log_warnings=False)
    assert float(out["trainer_14d_strike"].iloc[0]) == 0.22
    cols = ranker_tracker_feature_columns()
    assert len(cols) == EXPECTED_TRACKER_FEATURE_COUNT
    for feat in HORSE_TRACKER_RANKER_FEATURES:
        assert feat in cols


def test_attach_horse_tracker_features_pit(tmp_path):
    db = tmp_path / "race.sqlite"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE horse_form_state (
            horse_id TEXT, as_of_date TEXT, ewma_speed_delta REAL,
            speed_delta_lto REAL, sample_uncertainty REAL,
            runs_90d INTEGER, last_race_id TEXT, meta_json TEXT, updated_at TEXT,
            PRIMARY KEY (horse_id, as_of_date)
        );
        """
    )
    upsert_horse_state(
        conn,
        horse_id="H1",
        as_of_date="2026-01-05",
        ewma_speed_delta=1.2,
        speed_delta_lto=1.5,
        sample_uncertainty=0.3,
        runs_90d=4,
        last_race_id="R0",
    )
    conn.commit()

    frame = pd.DataFrame(
        [{"horse_id": "H1", "race_date": "2026-01-10", "runner_id": "U1", "race_id": "R1"}]
    )
    out = attach_horse_tracker_features(frame, conn)
    assert out.loc[0, "ewma_speed_delta"] == 1.2
    assert out.loc[0, "speed_delta_lto"] == 1.5


def test_tracker_manifest_json_exists():
    path = Path(__file__).resolve().parents[1] / "data" / "models" / "lgbm_ranker_features_tracker.json"
    assert path.is_file()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert len(payload["features"]) == EXPECTED_TRACKER_FEATURE_COUNT


def test_impute_horse_tracker_defaults():
    frame = pd.DataFrame([{"horse_id": "X"}])
    out = impute_horse_tracker_features(frame)
    assert out.loc[0, "ewma_speed_delta"] == 0.0


def test_racing_ranker_v2_gate():
    from hibs_racing.engine_adapter_promotion import evaluate_racing_ranker_v2_gate

    report = evaluate_racing_ranker_v2_gate(min_samples=1)
    assert report["schema"] == "racing_ranker_v2_v1"
