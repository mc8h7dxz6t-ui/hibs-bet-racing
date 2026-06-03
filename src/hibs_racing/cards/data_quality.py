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
        checks.append(row.get("form_string") or row.get("horse_course_win_rate"))
    ok = 0
    for val in checks:
        if val is None or (isinstance(val, float) and pd.isna(val)):
            continue
        if str(val).strip():
            ok += 1
    return int(round(100 * ok / max(len(checks), 1)))
