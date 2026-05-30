import sqlite3

import pytest

from hibs_racing.features.store import init_db
from hibs_racing.place.paper_ledger import (
    ledger_stats,
    record_paper_bet,
    settle_paper_bets,
)


def test_settle_paper_from_results(tmp_path, monkeypatch):
    db = tmp_path / "t.sqlite"
    monkeypatch.setenv("HIBS_RACING_DB_PATH", str(db))
    init_db(db)

    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            INSERT INTO upcoming_runners (
                runner_id, race_id, card_date, horse_id, horse_name, course, source, fetched_at
            ) VALUES ('R1:test_horse', 'R1', '2026-05-30', 'Test Horse', 'Test Horse', 'Ascot', 'test', 'now')
            """
        )
        conn.execute(
            """
            INSERT INTO runners (
                runner_id, race_id, horse_id, race_date, course, finish_pos, comment_raw, comment_norm, ingested_at
            ) VALUES ('hist1', 'R1', 'Test Horse', '2026-05-30', 'Ascot', 2, 'ok', 'ok', 'now')
            """
        )
        conn.commit()

    record_paper_bet("R1", "R1:test_horse", "each_way", 1.0, offered_win=8.0, is_value_pick=True, database=db)
    result = settle_paper_bets(database=db)

    assert result["settled"] == 1
    stats = ledger_stats(db)
    assert stats.settled_bets == 1
    assert stats.place_hits == 1
    assert stats.value_pick_hits == 1
    assert stats.value_pick_strike == 1.0
    assert stats.total_pnl != 0


def test_settle_paper_fallback_by_horse_date(tmp_path, monkeypatch):
    db = tmp_path / "t.sqlite"
    monkeypatch.setenv("HIBS_RACING_DB_PATH", str(db))
    init_db(db)

    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            INSERT INTO upcoming_runners (
                runner_id, race_id, card_date, horse_id, horse_name, course, source, fetched_at
            ) VALUES ('api_id:hope_rising', 'api-999', '2026-05-30', 'Hope Rising', 'Hope Rising', 'Stratford', 'test', 'now')
            """
        )
        conn.execute(
            """
            INSERT INTO runners (
                runner_id, race_id, horse_id, race_date, course, finish_pos, comment_raw, comment_norm, ingested_at
            ) VALUES ('rf1', 'rf-123', 'Hope Rising', '2026-05-30', 'Stratford', 3, 'ok', 'ok', 'now')
            """
        )
        conn.commit()

    record_paper_bet("api-999", "api_id:hope_rising", "each_way", 1.0, offered_win=6.0, is_value_pick=True, database=db)
    result = settle_paper_bets(database=db)
    assert result["settled"] == 1
    assert result["details"][0]["finish_pos"] == 3


def test_settle_paper_natural_key_cross_source(tmp_path, monkeypatch):
    from hibs_racing.entity.natural_key import generate_natural_key

    db = tmp_path / "t.sqlite"
    monkeypatch.setenv("HIBS_RACING_DB_PATH", str(db))
    init_db(db)
    nk = generate_natural_key("2026-05-30", "Newcastle (AW)", "15:30")

    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            INSERT INTO upcoming_runners (
                runner_id, race_id, card_date, off_time, course, horse_id, horse_name,
                race_natural_key, source, fetched_at
            ) VALUES ('api:star_runner', 'api-race-1', '2026-05-30', '15:30', 'Newcastle (AW)',
                      'Star Runner', 'Star Runner', ?, 'test', 'now')
            """,
            (nk,),
        )
        conn.execute(
            """
            INSERT INTO runners (
                runner_id, race_id, horse_id, race_date, course, off_time, race_natural_key,
                finish_pos, comment_raw, comment_norm, ingested_at
            ) VALUES ('rf:99', 'rf-diff-id', 'Star Runner', '2026-05-30', 'Newcastle', '15:30', ?, 2, 'ok', 'ok', 'now')
            """,
            (nk,),
        )
        conn.commit()

    record_paper_bet("api-race-1", "api:star_runner", "each_way", 1.0, offered_win=5.0, database=db)
    result = settle_paper_bets(database=db)
    assert result["settled"] == 1
    assert result["details"][0]["finish_pos"] == 2

