"""Tests for racing DQ-max persistence."""

from __future__ import annotations

import pandas as pd

from hibs_racing.cards.dq_persist import merge_runners_preserve_best, mean_runner_dq


def test_merge_runners_preserves_higher_dq():
    existing = pd.DataFrame(
        [
            {
                "runner_id": "r1",
                "horse_name": "Alpha",
                "win_decimal": 3.5,
                "official_rating": 110,
                "form_string": "112",
            }
        ]
    )
    incoming = pd.DataFrame(
        [
            {
                "runner_id": "r1",
                "horse_name": "Alpha",
                "win_decimal": None,
                "official_rating": 90,
                "form_string": None,
            }
        ]
    )
    merged = merge_runners_preserve_best(existing, incoming)
    row = merged.iloc[0].to_dict()
    assert row["official_rating"] == 110
    assert row["win_decimal"] == 3.5


def test_merge_runners_keeps_existing_not_in_incoming():
    existing = pd.DataFrame(
        [
            {"runner_id": "r1", "horse_name": "A", "win_decimal": 4.0},
            {"runner_id": "r2", "horse_name": "B", "win_decimal": 5.0},
        ]
    )
    incoming = pd.DataFrame([{"runner_id": "r1", "horse_name": "A", "win_decimal": 3.0}])
    merged = merge_runners_preserve_best(existing, incoming)
    assert len(merged) == 2
    assert mean_runner_dq(merged) >= mean_runner_dq(existing)


def test_store_prunes_off_window_dates(tmp_path, monkeypatch):
    from hibs_racing.cards.store import load_upcoming_runners, store_upcoming_runners
    from hibs_racing.config import db_path, load_config
    from hibs_racing.features.store import init_db

    db = tmp_path / "cards.db"
    monkeypatch.setattr("hibs_racing.cards.store.db_path", lambda _cfg=None: db)
    monkeypatch.setattr("hibs_racing.cards.dq_persist.preserve_best_dq_enabled", lambda: True)

    init_db(db)
    stale = pd.DataFrame(
        [
            {
                "runner_id": "old1",
                "race_id": "ra",
                "card_date": "2026-07-29",
                "horse_id": "h1",
                "horse_name": "Stale",
                "win_decimal": 4.0,
            }
        ]
    )
    store_upcoming_runners(stale, source="seed", database=db)

    incoming = pd.DataFrame(
        [
            {
                "runner_id": "new1",
                "race_id": "rb",
                "card_date": "2026-07-31",
                "horse_id": "h2",
                "horse_name": "Fresh",
                "win_decimal": 5.0,
            }
        ]
    )
    store_upcoming_runners(incoming, source="refresh", database=db)
    out = load_upcoming_runners(database=db)
    assert len(out) == 1
    assert out.iloc[0]["runner_id"] == "new1"


def test_day_offsets_for_card_dates(monkeypatch):
    from datetime import date

    from hibs_racing.cards.enrich import _day_offsets_for_card_dates

    class _FixedDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 7, 31)

    monkeypatch.setattr("hibs_racing.cards.enrich.date", _FixedDate)
    assert _day_offsets_for_card_dates(["2026-07-31"]) == [1]
    assert _day_offsets_for_card_dates(["2026-07-31", "2026-08-01"]) == [1, 2]
