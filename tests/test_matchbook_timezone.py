from datetime import datetime
from zoneinfo import ZoneInfo

from hibs_racing.entity.natural_key import generate_natural_key
from hibs_racing.entity.timezone import matchbook_event_local_date, normalize_matchbook_time_to_london
from hibs_racing.odds.matchbook import _card_day_window, _event_course_hint, build_matchbook_natural_key


def test_bst_offset_summer():
    # 14:30 UTC = 15:30 BST (last Sunday in May → Oct)
    assert normalize_matchbook_time_to_london("2026-06-15T14:30:00.000Z") == "15:30"
    assert matchbook_event_local_date("2026-06-15T14:30:00.000Z") == "2026-06-15"


def test_gmt_winter():
    assert normalize_matchbook_time_to_london("2026-01-15T14:30:00.000Z") == "14:30"


def test_build_matchbook_natural_key_bst():
    event = {
        "start": "2026-06-15T14:30:00.000Z",
        "name": "15:30 York",
        "meta-tags": [{"type": "VENUE", "name": "York"}],
    }
    key = build_matchbook_natural_key(event)
    assert key == generate_natural_key("2026-06-15", "York", "15:30")


def test_card_day_window_uses_london_calendar_day():
    import pandas as pd

    cards = pd.DataFrame([{"card_date": "2026-06-15"}])
    after, before = _card_day_window(cards)
    # 2026-06-15 00:00 BST = 2026-06-14 23:00 UTC
    assert after == int(datetime(2026, 6, 14, 23, 0, tzinfo=ZoneInfo("UTC")).timestamp())
    # 2026-06-15 23:59:59 BST = 2026-06-15 22:59:59 UTC
    assert before == int(datetime(2026, 6, 15, 22, 59, 59, tzinfo=ZoneInfo("UTC")).timestamp())
