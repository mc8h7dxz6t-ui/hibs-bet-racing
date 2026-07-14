"""Tests for racing data producer SLO."""

from __future__ import annotations

from unittest.mock import patch


def test_build_data_producer_snapshot_shape():
    from hibs_racing.data_producer_slo import build_data_producer_snapshot

    with patch(
        "hibs_racing.data_producer_slo.card_store_status",
        return_value={"ok": True, "runner_count": 10, "card_fresh": True},
    ), patch(
        "hibs_racing.data_producer_slo.robust_scrape_status",
        return_value={"ok": True},
    ):
        snap = build_data_producer_snapshot()
    assert snap["layer"] == "racing_data_producer_slo"
    assert snap["ok"] is True
    assert "racing_cards" in snap["producers"]


def test_health_includes_data_producer(monkeypatch):
    from hibs_racing.web_service import health_status

    monkeypatch.setenv("HIBS_HEALTH_LIGHT", "0")
    with patch(
        "hibs_racing.data_producer_slo.build_data_producer_snapshot",
        return_value={"ok": True, "layer": "racing_data_producer_slo"},
    ):
        payload = health_status().to_dict()
    assert payload.get("data_producer", {}).get("ok") is True


def test_paper_bet_status_by_runner(tmp_path, monkeypatch):
    import sqlite3

    from hibs_racing.features.store import init_db
    from hibs_racing.place.paper_ledger import paper_bet_status_by_runner, record_paper_bet

    db = tmp_path / "racing.sqlite"
    monkeypatch.setenv("HIBS_RACING_DB_PATH", str(db))
    init_db(db)
    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            INSERT INTO upcoming_runners (
                runner_id, race_id, card_date, horse_id, horse_name, course, source, fetched_at, off_time
            ) VALUES ('race1:star', 'race1', '2026-06-16', 'Star', 'Star', 'Ascot', 'test', 'now', '14:30')
            """
        )
        conn.commit()
    record_paper_bet("race1", "race1:star", "each_way", 1.0, is_value_pick=True, database=db)
    status = paper_bet_status_by_runner(card_dates=["2026-06-16"], database=db)
    assert status["race1:star"]["status"] == "open"
    assert status["race1:star"]["is_value_pick"] is True
