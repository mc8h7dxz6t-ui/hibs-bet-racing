from __future__ import annotations

import re
from datetime import datetime, timedelta

import pandas as pd

from hibs_racing.entity.timezone import LONDON

_TIME_RE = re.compile(r"(\d{1,2}):(\d{2})")


def off_minutes(off_time: object) -> int:
    if off_time is None or (isinstance(off_time, float) and pd.isna(off_time)):
        return 9999
    text = str(off_time).strip()
    m = _TIME_RE.search(text)
    if not m:
        return 9999
    return int(m.group(1)) * 60 + int(m.group(2))


def runner_off_dt(card_date: object, off_time: object) -> datetime | None:
    if card_date is None or (isinstance(card_date, float) and pd.isna(card_date)):
        return None
    date_s = str(card_date)[:10]
    try:
        base = datetime.strptime(date_s, "%Y-%m-%d").replace(tzinfo=LONDON)
    except ValueError:
        return None
    mins = off_minutes(off_time)
    if mins >= 9999:
        return base.replace(hour=12, minute=0)
    return base.replace(hour=mins // 60, minute=mins % 60, second=0, microsecond=0)


def filter_next_hours(frame: pd.DataFrame, *, hours: int = 24) -> pd.DataFrame:
    """Keep runners whose off time falls within the next N hours (Europe/London)."""
    if frame.empty:
        return frame
    now = datetime.now(LONDON)
    cutoff = now + timedelta(hours=hours)
    keep: list[bool] = []
    for _, row in frame.iterrows():
        off = runner_off_dt(row.get("card_date"), row.get("off_time"))
        if off is None:
            keep.append(True)
        else:
            keep.append(now - timedelta(minutes=30) <= off <= cutoff)
    return frame.loc[keep].copy()
