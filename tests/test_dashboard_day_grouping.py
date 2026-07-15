"""Dashboard day grouping for racecards and picks."""

from __future__ import annotations

import pandas as pd

from hibs_racing.web_service import day_label, group_meetings_by_day, top_picks_by_day


def test_day_label_today_tomorrow():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    uk = ZoneInfo("Europe/London")
    now = datetime(2026, 7, 14, 12, 0, tzinfo=uk)
    today = now.date().isoformat()
    tomorrow = "2026-07-15"
    assert day_label(today, now=now) == "Today"
    assert day_label(tomorrow, now=now) == "Tomorrow"
    assert day_label("2026-07-20", now=now) == "2026-07-20"


def test_group_meetings_by_day_orders_dates():
    meetings = [
        {"card_date": "2026-07-15", "course": "York", "slug": "1-york"},
        {"card_date": "2026-07-14", "course": "Ascot", "slug": "2-ascot"},
    ]
    days = group_meetings_by_day(meetings)
    assert [d["card_date"] for d in days] == ["2026-07-14", "2026-07-15"]
    assert days[0]["meetings"][0]["course"] == "Ascot"


def test_top_picks_by_day_splits_frame(monkeypatch):
    frame = pd.DataFrame(
        [
            {
                "card_date": "2026-07-14",
                "race_id": "r1",
                "runner_id": "r1:a",
                "horse_name": "Alpha",
                "field_size": 8,
                "model_place_prob": 0.55,
                "combo_bayes_place": 0.4,
                "off_time": "14:00",
                "course": "Ascot",
            },
            {
                "card_date": "2026-07-15",
                "race_id": "r2",
                "runner_id": "r2:b",
                "horse_name": "Bravo",
                "field_size": 8,
                "model_place_prob": 0.6,
                "combo_bayes_place": 0.42,
                "off_time": "15:00",
                "course": "York",
            },
        ]
    )
    meetings = [{"card_date": "2026-07-14", "course": "Ascot", "slug": "1", "races": []}]
    out = top_picks_by_day(frame, meetings, top_n=3)
    assert "2026-07-14" in out and "2026-07-15" in out
    assert out["2026-07-14"][0]["horse_name"] == "Alpha"
    assert out["2026-07-15"][0]["horse_name"] == "Bravo"
