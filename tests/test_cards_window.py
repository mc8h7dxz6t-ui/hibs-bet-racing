import pandas as pd

from hibs_racing.cards.window import filter_next_hours, off_minutes, primary_card_date, runner_off_dt


def test_off_minutes():
    assert off_minutes("14:30") == 14 * 60 + 30
    assert off_minutes("6:15") == 18 * 60 + 15
    assert off_minutes("bad") == 9999


def test_filter_next_hours_drops_rows_without_card_date():
    frame = pd.DataFrame(
        [
            {"card_date": None, "off_time": "14:00", "runner_id": "bad"},
            {"card_date": "2099-01-01", "off_time": "12:00", "runner_id": "far"},
        ]
    )
    out = filter_next_hours(frame, hours=24)
    assert out.empty


def test_filter_next_hours_keeps_imminent_races():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    uk = ZoneInfo("Europe/London")
    today = datetime.now(uk).date().isoformat()
    frame = pd.DataFrame(
        [
            {"card_date": today, "off_time": "23:59", "runner_id": "a"},
            {"card_date": "2099-01-01", "off_time": "12:00", "runner_id": "b"},
        ]
    )
    out = filter_next_hours(frame, hours=24)
    assert "a" in out["runner_id"].values
    assert "b" not in out["runner_id"].values


def test_runner_off_dt():
    dt = runner_off_dt("2026-05-30", "15:30")
    assert dt is not None
    assert dt.hour == 15 and dt.minute == 30


def test_primary_card_date_rolls_to_tomorrow_when_today_finished():
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    uk = ZoneInfo("Europe/London")
    now = datetime(2026, 7, 10, 21, 0, tzinfo=uk)
    today = now.date().isoformat()
    tomorrow = (now.date() + timedelta(days=1)).isoformat()
    frame = pd.DataFrame(
        [
            {"card_date": today, "off_time": "14:00", "runner_id": "done"},
            {"card_date": tomorrow, "off_time": "14:30", "runner_id": "next"},
        ]
    )
    assert primary_card_date(frame, now=now) == tomorrow


def test_primary_card_date_keeps_today_while_races_remain():
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    uk = ZoneInfo("Europe/London")
    now = datetime(2026, 7, 10, 16, 0, tzinfo=uk)
    today = now.date().isoformat()
    tomorrow = (now.date() + timedelta(days=1)).isoformat()
    frame = pd.DataFrame(
        [
            {"card_date": today, "off_time": "18:00", "runner_id": "today"},
            {"card_date": tomorrow, "off_time": "14:30", "runner_id": "next"},
        ]
    )
    assert primary_card_date(frame, now=now) == today
