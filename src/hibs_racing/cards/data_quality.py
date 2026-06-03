"""Runner-level data completeness — shared by UI, gates, and paper audit."""

from __future__ import annotations

import re

import pandas as pd

_UNRATED_RACE_RE = re.compile(
    r"\b(maiden|novices?|nursery|seller|introductory|amateur|conditional\s+jockeys)\b",
    re.I,
)


def is_exempt_unrated_race(row: pd.Series | dict) -> bool:
    """Maidens/novices etc. — no OR expected; rank-only for value/paper."""
    if isinstance(row, dict):
        row = pd.Series(row)
    name = str(row.get("race_name") or "")
    return bool(_UNRATED_RACE_RE.search(name))


def _present(val: object) -> bool:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return False
    return bool(str(val).strip())


def _first_present(row: pd.Series, *keys: str) -> object | None:
    for key in keys:
        val = row.get(key)
        if _present(val):
            return val
    return None


def runner_data_quality_pct(row: pd.Series | dict) -> int:
    """
    Percentage of required display/actionability fields present.
    Maidens skip OR/comment penalties; enrich rows expect form or course stats.
    """
    if isinstance(row, dict):
        row = pd.Series(row)
    exempt = is_exempt_unrated_race(row)
    checks: list[object] = [
        row.get("win_decimal"),
        row.get("model_win_prob"),
        row.get("model_place_prob"),
        row.get("jockey"),
        row.get("trainer"),
    ]
    if not exempt:
        checks.extend([row.get("card_comment"), row.get("official_rating")])
    if row.get("enrich_source"):
        checks.append(_first_present(row, "form_string", "horse_course_win_rate"))
    ok = 0
    for val in checks:
        if not _present(val):
            continue
        ok += 1
    return int(round(100 * ok / max(len(checks), 1)))
