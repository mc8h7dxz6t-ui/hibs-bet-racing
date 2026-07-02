"""Paper settlement must survive upcoming_runners refresh (denormalized context)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from hibs_racing.features.store import init_db
from hibs_racing.place.paper_ledger import record_paper_bet, settle_paper_bets


def _seed_runners(db: Path) -> None:
    init_db(db)
    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            INSERT INTO runners (
                runner_id, race_id, race_date, horse_id, course, off_time,
                race_natural_key, finish_pos, ingested_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "r1:h1",
                "race1",
                "2026-06-15",
                "h1",
                "Ascot",
                "14:30",
                "2026-06-15|ascot|14:30",
                1,
                "2026-06-16T00:00:00+00:00",
            ),
        )
        conn.commit()


def test_settle_open_bet_without_upcoming_runners(tmp_path: Path) -> None:
    db = tmp_path / "feature_store.sqlite"
    _seed_runners(db)
    record_paper_bet(
        "race1",
        "r1:h1",
        "each_way",
        1.0,
        offered_win=5.0,
        place_terms="1/4 top 3",
        is_value_pick=True,
        backtest=False,
        database=db,
    )
    with sqlite3.connect(db) as conn:
        conn.execute("DELETE FROM upcoming_runners")
        conn.commit()
    out = settle_paper_bets(database=db)
    assert out["settled"] == 1
    assert out["stats"]["settled_bets"] == 1
    assert out["stats"]["roi_pct"] is not None
