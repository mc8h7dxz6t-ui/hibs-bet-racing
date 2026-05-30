from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

LONDON = ZoneInfo("Europe/London")

__all__ = ["LONDON", "matchbook_event_local_date", "normalize_matchbook_time_to_london"]


def normalize_matchbook_time_to_london(utc_time_str: str | None) -> str:
    """
    Matchbook ISO UTC → UK local HH:MM for natural-key alignment with cards.
    Example: 2026-05-30T14:30:00.000Z (BST) → 15:30
    """
    if not utc_time_str:
        return "00:00"
    text = str(utc_time_str).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    london_dt = dt.astimezone(LONDON)
    return london_dt.strftime("%H:%M")


def matchbook_event_local_date(utc_time_str: str | None) -> str | None:
    """UK calendar date for a Matchbook event start (handles midnight edge cases)."""
    if not utc_time_str:
        return None
    text = str(utc_time_str).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return utc_time_str.split("T")[0] if "T" in utc_time_str else None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt.astimezone(LONDON).date().isoformat()
