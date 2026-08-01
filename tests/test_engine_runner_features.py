"""Materialized engine_runner_features store."""

from __future__ import annotations

import sqlite3

import pandas as pd

from hibs_racing.features.engine_runner_store import (
    engine_runner_store_status,
    materialize_engine_runner_features,
    sync_racing_engine_store_from_scored_cards,
    upsert_engine_runner_feature,
)


def _runner_row(**overrides):
    base = {
        "runner_id": "r-100",
        "race_id": "race-1",
        "race_natural_key": "2026-08-15|Ascot|14:30",
        "card_date": "2026-08-15",
        "course": "Ascot",
        "off_time": "14:30",
        "horse_name": "Test Horse",
        "jockey": "J Bloggs",
        "trainer": "T Smith",
        "official_rating": 95,
        "win_decimal": 5.0,
        "model_score": 0.72,
        "model_win_prob": 0.18,
        "model_place_prob": 0.42,
        "combo_bayes_place": 0.35,
        "form_string": "1234",
        "trainer_rtf": 0.55,
        "horse_course_win_rate": 0.2,
        "enrich_source": "dual_source",
        "value_flag": 1,
        "scoring_method": "lgbm_ranker",
    }
    base.update(overrides)
    return base


def test_materialize_engine_runner_features(tmp_path, monkeypatch):
    db = tmp_path / "feature_store.sqlite"
    monkeypatch.setenv("HIBS_RACING_DB_PATH", str(db))
    frame = pd.DataFrame([_runner_row()])
    stats = materialize_engine_runner_features(frame, database=db)
    assert stats["written"] == 1

    with sqlite3.connect(str(db)) as conn:
        n = conn.execute("SELECT COUNT(*) FROM engine_runner_features").fetchone()[0]
    assert n == 1


def test_sync_racing_engine_store_from_scored_cards(tmp_path, monkeypatch):
    db = tmp_path / "feature_store.sqlite"
    monkeypatch.setenv("HIBS_RACING_DB_PATH", str(db))
    frame = pd.DataFrame([_runner_row()])
    monkeypatch.setattr(
        "hibs_racing.cards.query.load_scored_cards",
        lambda **kwargs: frame,
    )
    out = sync_racing_engine_store_from_scored_cards(database=db)
    assert out["ok"] is True
    assert out["engine_written"] == 1
    status = engine_runner_store_status(database=db)
    assert status["runner_rows"] == 1
