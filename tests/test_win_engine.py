"""Tests for McFadden win engine — schema, softmax, circuit breaker."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from hibs_racing.features.store import connect, init_db
from hibs_racing.models.win_engine_circuit import evaluate_calibration_circuit, sync_brier_from_runners
from hibs_racing.models.win_engine_config import win_engine_active
from hibs_racing.models.win_engine_service import mcfadden_conditional_logit, run_win_engine
from hibs_racing.models.win_engine_store import ensure_win_engine_schema, load_calibration_state, upsert_predictions


def test_mcfadden_probabilities_sum_to_one():
    frame = pd.DataFrame(
        {
            "race_id": ["R1", "R1", "R1", "R2", "R2"],
            "runner_id": ["a", "b", "c", "d", "e"],
            "x_fund": [2.0, 1.0, 0.5, 1.2, 0.8],
            "live_odds_decimal": [3.0, 5.0, 8.0, 4.0, 6.0],
        }
    )
    out = mcfadden_conditional_logit(frame)
    for race_id, group in out.groupby("race_id"):
        total = float(group["true_probability"].sum())
        assert total == pytest.approx(1.0, abs=1e-6)
        assert (group["fair_odds"] > 1.0).all()


def test_win_engine_schema_and_upsert(tmp_path):
    db = tmp_path / "feature_store.sqlite"
    init_db(db)
    ensure_win_engine_schema(db)
    rows = [
        {
            "runner_id": "R1:h1",
            "race_id": "R1",
            "true_probability": 0.25,
            "fair_odds": 4.0,
            "place_probability": 0.45,
            "live_odds_decimal": 5.0,
            "x_fund": 1.1,
            "market_velocity": 0.2,
        }
    ]
    with connect(db) as conn:
        n = upsert_predictions(conn, rows)
        assert n == 1
        state = load_calibration_state(conn)
        assert state["calibration_state"] == "UNCALIBRATED"


def test_circuit_breaker_trips_on_high_brier(tmp_path, monkeypatch):
    monkeypatch.setenv("HIBS_RACING_WIN_BRIER_PASS_MAX", "0.185")
    monkeypatch.setenv("HIBS_RACING_MIN_WIN_CALIBRATION_N", "3")
    db = tmp_path / "feature_store.sqlite"
    init_db(db)
    ensure_win_engine_schema(db)
    with connect(db) as conn:
        for i in range(5):
            conn.execute(
                """
                INSERT INTO win_engine_predictions (
                    runner_id, race_id, true_probability, fair_odds, brier_score, timestamp
                ) VALUES (?, ?, ?, ?, ?, datetime('now'))
                """,
                (f"r{i}", f"race{i}", 0.9, 1.11, 0.25,),
            )
    out = evaluate_calibration_circuit(db)
    assert out["calibration_state"] == "UNCALIBRATED"


def test_win_engine_active_default_false(monkeypatch):
    monkeypatch.delenv("HIBS_WIN_ENGINE_ACTIVE", raising=False)
    assert win_engine_active() is False


def test_win_engine_env_true_blocked_without_calibration(tmp_path, monkeypatch):
    from hibs_racing.config import db_path, load_config
    from hibs_racing.models.win_engine_config import win_engine_env_requested

    monkeypatch.setenv("HIBS_WIN_ENGINE_ACTIVE", "true")
    monkeypatch.setenv("HIBS_RACING_DB_PATH", str(tmp_path / "feature_store.sqlite"))
    db = tmp_path / "feature_store.sqlite"
    init_db(db)
    ensure_win_engine_schema(db)
    assert win_engine_env_requested() is True
    assert win_engine_active() is False


def test_win_engine_active_when_calibrated(tmp_path, monkeypatch):
    from hibs_racing.models.win_engine_store import update_calibration_state

    monkeypatch.setenv("HIBS_WIN_ENGINE_ACTIVE", "true")
    monkeypatch.setenv("HIBS_RACING_DB_PATH", str(tmp_path / "feature_store.sqlite"))
    monkeypatch.setenv("HIBS_RACING_WIN_BRIER_PASS_MAX", "0.185")
    monkeypatch.setenv("HIBS_RACING_MIN_WIN_CALIBRATION_N", "100")
    db = tmp_path / "feature_store.sqlite"
    init_db(db)
    ensure_win_engine_schema(db)
    with connect(db) as conn:
        update_calibration_state(
            conn,
            calibration_state="CALIBRATED",
            rolling_brier=0.12,
            sample_n=150,
            races_in_window=40,
        )
        conn.commit()
    assert win_engine_active() is True


def test_run_win_engine_on_minimal_cards(tmp_path, monkeypatch):
    monkeypatch.setenv("HIBS_RACING_PRODUCTION", "0")
    db = tmp_path / "feature_store.sqlite"
    init_db(db)
    cards = pd.DataFrame(
        {
            "runner_id": ["R1:a", "R1:b"],
            "race_id": ["R1", "R1"],
            "horse_id": ["a", "b"],
            "card_date": ["2026-07-16", "2026-07-16"],
            "course": ["York", "York"],
            "off_time": ["14:00", "14:00"],
            "field_size": [2, 2],
            "win_decimal": [3.5, 4.0],
            "official_rating": [90, 85],
            "rpr": [95, 88],
            "jockey": ["J1", "J2"],
            "trainer": ["T1", "T2"],
            "race_class": ["Class 3", "Class 3"],
            "race_type": ["Flat", "Flat"],
            "going": ["Good", "Good"],
            "distance_f": [8.0, 8.0],
        }
    )
    with connect(db) as conn:
        for _, row in cards.iterrows():
            conn.execute(
                """
                INSERT INTO upcoming_runners (
                    runner_id, race_id, card_date, off_time, course, horse_id, horse_name,
                    field_size, win_decimal, official_rating, rpr, jockey, trainer, source, fetched_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                """,
                (
                    row["runner_id"],
                    row["race_id"],
                    row["card_date"],
                    row["off_time"],
                    row["course"],
                    row["horse_id"],
                    row["horse_id"],
                    row["field_size"],
                    row["win_decimal"],
                    row["official_rating"],
                    row["rpr"],
                    row["jockey"],
                    row["trainer"],
                    "test",
                ),
            )
    out = run_win_engine(cards, database=db, persist=True)
    assert len(out) == 2
    assert float(out["true_probability"].sum()) == pytest.approx(1.0, abs=1e-5)
    with connect(db) as conn:
        n = conn.execute("SELECT COUNT(*) FROM win_engine_predictions").fetchone()[0]
        assert n == 2
