"""Tests for extended McFadden win engine backtest."""

from __future__ import annotations

import pandas as pd
import pytest

from hibs_racing.backtest.win_engine_backtest import run_win_engine_backtest
from hibs_racing.features.store import connect, init_db


def _seed_historical_runners(db, *, card_date: str = "2026-05-15") -> None:
    ingested_at = "2026-05-16T00:00:00+00:00"
    rows = [
        ("R1:a", "R1", "h1", card_date, "14:00", "York", "GB", "flat", "Class 3", "Good", 2, 8.0, 90, 95, "J1", "T1", 3.5, 1),
        ("R1:b", "R1", "h2", card_date, "14:00", "York", "GB", "flat", "Class 3", "Good", 2, 8.0, 85, 88, "J2", "T2", 5.0, 2),
        ("R2:c", "R2", "h3", card_date, "15:00", "Ascot", "GB", "flat", "Class 2", "Good To Firm", 2, 7.0, 100, 102, "J3", "T3", 2.5, 1),
        ("R2:d", "R2", "h4", card_date, "15:00", "Ascot", "GB", "flat", "Class 2", "Good To Firm", 2, 7.0, 92, 90, "J4", "T4", 4.0, 2),
    ]
    with connect(db) as conn:
        for row in rows:
            conn.execute(
                """
                INSERT INTO runners (
                    runner_id, race_id, horse_id, race_date, off_time, course, region, race_type,
                    race_class, going, field_size, distance_f, official_rating, rpr,
                    jockey, trainer, sp_decimal, finish_pos, ingested_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                row + (ingested_at,),
            )


def test_win_engine_backtest_on_historical_runners(tmp_path, monkeypatch):
    pytest.importorskip("sklearn")
    monkeypatch.setenv("HIBS_RACING_PRODUCTION", "0")
    db = tmp_path / "feature_store.sqlite"
    init_db(db)
    _seed_historical_runners(db)

    report = run_win_engine_backtest(
        start="2026-05-15",
        end="2026-05-15",
        database=db,
        extended=True,
    )

    assert report.runners >= 4
    assert report.mean_brier is not None
    assert report.top1_picks >= 2
    assert report.calibration_bins
    assert "Brier=" in report.message


def test_win_engine_backtest_seed_calibration(tmp_path, monkeypatch):
    pytest.importorskip("sklearn")
    monkeypatch.setenv("HIBS_RACING_PRODUCTION", "0")
    monkeypatch.setenv("HIBS_RACING_WIN_BRIER_PASS_MAX", "0.99")
    db = tmp_path / "feature_store.sqlite"
    init_db(db)
    _seed_historical_runners(db)

    run_win_engine_backtest(
        start="2026-05-15",
        end="2026-05-15",
        database=db,
        seed_calibration=True,
    )

    with connect(db) as conn:
        row = conn.execute(
            "SELECT calibration_state, rolling_brier, sample_n FROM win_engine_calibration WHERE id=1"
        ).fetchone()
    assert row is not None
    assert int(row["sample_n"]) >= 4
