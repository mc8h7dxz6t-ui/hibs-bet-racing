from __future__ import annotations

import re

_TIME_RE = re.compile(r"(\d{1,2}):(\d{2})")


def normalize_course(course: str | None) -> str:
    """Newcastle (AW) → newcastle; strip punctuation for join keys."""
    if not course:
        return ""
    base = str(course).lower().split("(")[0].strip()
    slug = re.sub(r"[^a-z0-9]+", "_", base).strip("_")
    return slug or base.replace(" ", "_")


def normalize_off_time(off_time: str | None) -> str:
    """14:30:00 / 2:30pm → 14:30 (24h HH:MM)."""
    if not off_time:
        return "00:00"
    text = str(off_time).strip().lower()
    m = _TIME_RE.search(text)
    if not m:
        return "00:00"
    hour = int(m.group(1))
    minute = m.group(2)
    if "pm" in text and hour < 12:
        hour += 12
    elif "am" in text and hour == 12:
        hour = 0
    elif "am" not in text and "pm" not in text and 1 <= hour <= 9:
        # Racing API free tier often omits am/pm (e.g. 6:15 → 18:15 UK).
        hour += 12
    return f"{hour:02d}:{minute}"


def generate_natural_key(
    date: str,
    course_string: str | None,
    scheduled_time: str | None,
) -> str:
    """Deterministic cross-source race identity: date + course + off time."""
    clean_course = normalize_course(course_string)
    clean_time = normalize_off_time(scheduled_time)
    return f"{date}_{clean_course}_{clean_time}"


def courses_match(a: str | None, b: str | None) -> bool:
    na, nb = normalize_course(a), normalize_course(b)
    if not na or not nb:
        return False
    return na == nb or na.startswith(nb) or nb.startswith(na)
