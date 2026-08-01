"""Settlement fallbacks when denormalized paper context was lost."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from hibs_racing.features.store import init_db
from hibs_racing.place.paper_ledger import record_paper_bet, settle_paper_bets


def _seed_result(
    db: Path,
    *,
    race_date: str = "2026-07-25",
    horse: str = "Lucky Star",
    course: str = "York",
    off_time: str = "15:30",
    finish_pos: int = 2,
) -> None:
    from hibs_racing.entity.natural_key import generate_natural_key

    nk = generate_natural_key(race_date, course, off_time)
    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            INSERT INTO runners (
                runner_id, race_id, horse_id, race_date, course, off_time,
                race_natural_key, finish_pos, comment_raw, comment_norm, ingested_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"rf:{horse.lower().replace(' ', '_')}",
                f"rf-race-{race_date}",
                horse,
                race_date,
                course,
                off_time,
                nk,
                finish_pos,
                "ok",
                "ok",
                "2026-07-26T00:00:00+00:00",
            ),
        )
        conn.commit()


def test_settle_open_bet_card_date_from_created_at(tmp_path: Path) -> None:
    db = tmp_path / "feature_store.sqlite"
    init_db(db)
    _seed_result(db)

    record_paper_bet(
        "api-race-999",
        "api-race-999:lucky_star",
        "each_way",
        1.0,
        offered_win=8.0,
        is_value_pick=True,
        backtest=False,
        created_at="2026-07-25T12:00:00+00:00",
        database=db,
    )
    with sqlite3.connect(db) as conn:
        conn.execute("DELETE FROM upcoming_runners")
        conn.execute(
            "UPDATE paper_bets SET card_date = NULL, horse_name = NULL, course = NULL, off_time = NULL, race_natural_key = NULL"
        )
        conn.commit()

    out = settle_paper_bets(database=db)
    assert out["settled"] == 1
    assert out["skip_reasons"]["no_card_date"] == 0
    assert out["details"][0]["finish_pos"] == 2


def test_settle_open_bet_guesses_card_date_from_results(tmp_path: Path) -> None:
    db = tmp_path / "feature_store.sqlite"
    init_db(db)
    _seed_result(db, horse="Bold Move")

    record_paper_bet(
        "api-race-1",
        "api-race-1:bold_move",
        "each_way",
        1.0,
        offered_win=6.0,
        is_value_pick=True,
        backtest=False,
        created_at="2026-07-20T08:00:00+00:00",
        database=db,
    )
    with sqlite3.connect(db) as conn:
        conn.execute("DELETE FROM upcoming_runners")
        conn.execute(
            "UPDATE paper_bets SET card_date = NULL, horse_name = NULL, course = NULL, off_time = NULL, race_natural_key = NULL"
        )
        conn.commit()

    out = settle_paper_bets(database=db)
    assert out["settled"] == 1
    assert out["skip_reasons"]["no_finish_pos"] == 0
