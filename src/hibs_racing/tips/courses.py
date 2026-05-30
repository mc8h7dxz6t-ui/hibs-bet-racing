from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from hibs_racing.config import ROOT


@lru_cache(maxsize=1)
def uk_course_names() -> tuple[str, ...]:
    """UK/IRE course names from vendor rpscrape (longest names first for matching)."""
    path = ROOT / "vendor" / "rpscrape" / "courses" / "_courses"
    if not path.exists():
        return _FALLBACK_COURSES
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return _FALLBACK_COURSES
    names: set[str] = set()
    for section in data.values():
        if isinstance(section, dict):
            for name in section.values():
                if isinstance(name, str) and name.strip():
                    base = re.sub(r"-AW$", "", name.strip(), flags=re.I)
                    names.add(base)
                    names.add(name.strip())
    ordered = sorted(names, key=len, reverse=True)
    return tuple(ordered) if ordered else _FALLBACK_COURSES


def find_course_in_text(text: str) -> str | None:
    lower = text.lower()
    for name in uk_course_names():
        if name.lower() in lower:
            return name
    return None


_FALLBACK_COURSES: tuple[str, ...] = (
    "Ascot",
    "Aintree",
    "Cheltenham",
    "Chester",
    "Doncaster",
    "Epsom",
    "Goodwood",
    "Haydock",
    "Kempton",
    "Lingfield",
    "Newbury",
    "Newcastle",
    "Sandown",
    "York",
    "Wolverhampton",
)
