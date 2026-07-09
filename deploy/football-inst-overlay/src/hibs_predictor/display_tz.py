"""Display timezone helpers — kickoff labels and calendar windows."""

from __future__ import annotations

import os
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

_DEFAULT_TZ = "Europe/London"


def display_timezone() -> ZoneInfo:
    key = (os.getenv("HIBS_DISPLAY_TZ") or _DEFAULT_TZ).strip() or _DEFAULT_TZ
    try:
        return ZoneInfo(key)
    except Exception:
        return ZoneInfo(_DEFAULT_TZ)


def display_tz_label() -> str:
    tz = display_timezone()
    return (os.getenv("HIBS_DISPLAY_TZ_LABEL") or str(tz)).strip() or str(tz)


def local_today() -> date:
    return datetime.now(display_timezone()).date()


def parse_kickoff_utc(raw: str | None) -> Optional[datetime]:
    if not raw:
        return None
    text = str(raw).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def attach_kickoff_display(row: Dict[str, Any]) -> Dict[str, Any]:
    """Add display kickoff fields to a fixture row."""
    ko = parse_kickoff_utc(row.get("kickoff_iso") or row.get("date"))
    tz = display_timezone()
    out = dict(row)
    if ko is None:
        out.setdefault("kickoff_display", "—")
        return out
    local = ko.astimezone(tz)
    out["kickoff_utc"] = ko.isoformat()
    out["kickoff_local"] = local.isoformat()
    out["kickoff_display"] = local.strftime("%a %d %b %H:%M")
    out["display_tz"] = str(tz)
    out["display_tz_label"] = display_tz_label()
    return out


def enrich_fixtures_kickoff(fixtures: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [attach_kickoff_display(fx) for fx in fixtures if isinstance(fx, dict)]


def day_heading_for_local_date(d: date) -> str:
    today = local_today()
    if d == today:
        return "Today"
    if d == today - timedelta(days=1):
        return "Yesterday"
    if d == today + timedelta(days=1):
        return "Tomorrow"
    return d.strftime("%A %d %B")


def fixture_window_start_utc(*, days_ahead: int = 0) -> datetime:
    tz = display_timezone()
    target = local_today() + timedelta(days=int(days_ahead))
    start_local = datetime.combine(target, time.min, tzinfo=tz)
    return start_local.astimezone(timezone.utc)


def fixture_window_end_utc(*, days_ahead: int = 0) -> datetime:
    tz = display_timezone()
    target = local_today() + timedelta(days=int(days_ahead))
    end_local = datetime.combine(target, time.max.replace(microsecond=0), tzinfo=tz)
    return end_local.astimezone(timezone.utc)
