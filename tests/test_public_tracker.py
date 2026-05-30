import sqlite3

import pytest

from hibs_racing.features.store import init_db
from hibs_racing.place.paper_ledger import (
    bet_verification_hash,
    record_paper_bet,
    settle_paper_bets,
)
from hibs_racing.place.public_tracker import build_public_tracker_dict, public_tracker_enabled


def test_public_tracker_enabled_default(monkeypatch):
    monkeypatch.delenv("HIBS_PUBLIC_TRACKER", raising=False)
    assert public_tracker_enabled() is True
    monkeypatch.setenv("HIBS_PUBLIC_TRACKER", "0")
    assert public_tracker_enabled() is False


def test_bet_verification_hash_stable():
    h = bet_verification_hash("id1", "2026-01-01T12:00:00+00:00", "r1:h1", 5.0, 1.0)
    assert len(h) == 64
    assert h == bet_verification_hash("id1", "2026-01-01T12:00:00+00:00", "r1:h1", 5.0, 1.0)


def test_record_paper_bet_dedup(tmp_path, monkeypatch):
    db = tmp_path / "t.sqlite"
    monkeypatch.setenv("HIBS_RACING_DB_PATH", str(db))
    init_db(db)
    a = record_paper_bet("R1", "R1:h1", "each_way", 1.0, offered_win=5.0, is_value_pick=True, database=db)
    b = record_paper_bet("R1", "R1:h1", "each_way", 1.0, offered_win=5.0, is_value_pick=True, database=db)
    assert a == b
    with sqlite3.connect(db) as conn:
        n = conn.execute("SELECT COUNT(*) FROM paper_bets").fetchone()[0]
    assert n == 1


def test_settle_stores_clv_and_public_tracker_curve(tmp_path, monkeypatch):
    db = tmp_path / "t.sqlite"
    monkeypatch.setenv("HIBS_RACING_DB_PATH", str(db))
    init_db(db)
    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            INSERT INTO upcoming_runners (
                runner_id, race_id, card_date, horse_id, horse_name, course, source, fetched_at
            ) VALUES ('R1:h1', 'R1', '2026-05-30', 'Star', 'Star Runner', 'Ascot', 'test', 'now')
            """
        )
        conn.execute(
            """
            INSERT INTO runners (
                runner_id, race_id, horse_id, race_date, course, finish_pos, sp_decimal,
                comment_raw, comment_norm, ingested_at
            ) VALUES ('hist', 'R1', 'Star Runner', '2026-05-30', 'Ascot', 2, 4.0, 'ok', 'ok', 'now')
            """
        )
        conn.commit()

    record_paper_bet("R1", "R1:h1", "each_way", 1.0, offered_win=6.0, is_value_pick=True, database=db)
    result = settle_paper_bets(database=db)
    assert result["settled"] == 1

    payload = build_public_tracker_dict(history_days=60, database=db)
    assert payload["public"] is True
    assert payload["read_only"] is True
    assert payload["stats"]["settled_bets"] == 1
    assert len(payload["pnl_curve"]) == 1
    row = payload["ledger_rows"][0]
    assert row["closing_sp"] == 4.0
    assert row["clv_beat"] == 1
    assert row["verification_hash"]
    assert payload["clv"]["clv_beat_rate_pct"] == 100.0


def test_public_tracker_api_404_when_disabled(monkeypatch):
    pytest.importorskip("flask")
    monkeypatch.setenv("HIBS_PUBLIC_TRACKER", "0")
    from hibs_racing.web import create_app

    app = create_app()
    client = app.test_client()
    assert client.get("/tracker").status_code == 404
    assert client.get("/api/tracker").status_code == 404
