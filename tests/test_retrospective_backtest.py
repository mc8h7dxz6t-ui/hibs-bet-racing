"""Retrospective backtest replay tests."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def mini_db(tmp_path: Path):
    from hibs_racing.features.store import connect, init_db

    db = tmp_path / "test.sqlite"
    init_db(db)
    rows = [
        # Day 1 — training history
        ("r1:h1", "r1", "h1", "2026-01-01", "Ascot", "GB", "flat", 8, 1, 4.0, "J A", "T A", 100, 90, 1),
        ("r1:h2", "r1", "h2", "2026-01-01", "Ascot", "GB", "flat", 8, 2, 6.0, "J B", "T B", 95, 85, 2),
        # Day 2 — backtest card
        ("r2:h1", "r2", "h1", "2026-01-02", "Ascot", "GB", "flat", 6, 1, 5.0, "J A", "T A", 102, 92, 1),
        ("r2:h2", "r2", "h2", "2026-01-02", "Ascot", "GB", "flat", 6, 3, 8.0, "J B", "T B", 90, 80, 2),
        ("r2:h3", "r2", "h3", "2026-01-02", "Ascot", "GB", "flat", 6, 2, 12.0, "J C", "T C", 88, 78, 3),
    ]
    with connect(db) as conn:
        for row in rows:
            conn.execute(
                """
                INSERT INTO runners (
                    runner_id, race_id, horse_id, race_date, course, region, race_type,
                    field_size, finish_pos, sp_decimal, jockey, trainer,
                    official_rating, rpr, draw, comment_raw, comment_norm, source_file, source_hash, ingested_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '', '', 'test', 'test', '2026-01-01')
                """,
                row,
            )
        conn.commit()
    return db


def test_backtest_replay_runs(mini_db: Path, monkeypatch):
    pytest.importorskip("lightgbm")
    from hibs_racing.backtest.retrospective import run_retrospective_backtest
    from hibs_racing.features.store import connect, init_db

    init_db(mini_db)
    report = run_retrospective_backtest(start="2026-01-02", end="2026-01-02", database=mini_db, replace=True)
    assert report.runners_scored == 3
    assert report.races_scored == 1
    assert report.top1_picks == 1
    with connect(mini_db) as conn:
        n = conn.execute("SELECT COUNT(*) FROM paper_bets WHERE backtest = 1").fetchone()[0]
    assert n >= 0
