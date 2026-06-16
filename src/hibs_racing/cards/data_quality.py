"""Runner-level data completeness — shared by UI, gates, and paper audit."""

from __future__ import annotations

import re
from typing import Any, Dict

import pandas as pd

_UNRATED_RACE_RE = re.compile(
    r"\b(maiden|novices?|nursery|seller|introductory|amateur|conditional\s+jockeys)\b",
    re.I,
)

# Block weights for institutional DQ (sum to 100 when all blocks apply).
DQ_BLOCKS: Dict[str, Dict[str, Any]] = {
    "pricing": {
        "weight": 35,
        "fields": ("win_decimal", "model_win_prob", "model_place_prob"),
    },
    "connections": {
        "weight": 20,
        "fields": ("jockey", "trainer"),
    },
    "handicap": {
        "weight": 20,
        "fields": ("official_rating", "card_comment"),
        "exempt_unrated": True,
    },
    "enrich": {
        "weight": 25,
        "fields": ("form_string", "horse_course_win_rate"),
        "requires_enrich_source": True,
    },
}


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


def runner_quality_blocks(row: pd.Series | dict) -> Dict[str, Dict[str, Any]]:
    """Block-level DQ for /api/runner and UI tooltips (no I/O)."""
    if isinstance(row, dict):
        row = pd.Series(row)
    exempt = is_exempt_unrated_race(row)
    blocks: Dict[str, Dict[str, Any]] = {}
    for block_id, spec in DQ_BLOCKS.items():
        if spec.get("exempt_unrated") and exempt:
            blocks[block_id] = {"pct": 100, "skipped": True, "reason": "unrated_race"}
            continue
        if spec.get("requires_enrich_source") and not _present(row.get("enrich_source")):
            blocks[block_id] = {"pct": 100, "skipped": True, "reason": "no_enrich"}
            continue
        fields = spec.get("fields") or ()
        present = [f for f in fields if _present(_first_present(row, f) if f == "form_string" else row.get(f))]
        pct = int(round(100 * len(present) / max(len(fields), 1)))
        blocks[block_id] = {
            "pct": pct,
            "present": present,
            "missing": [f for f in fields if f not in present],
            "weight": int(spec.get("weight") or 0),
        }
    return blocks


def runner_data_quality_pct(row: pd.Series | dict) -> int:
    """
    Weighted block DQ percentage. Maidens skip OR/comment penalties; enrich rows expect form or course stats.
    Falls back to simple field count when blocks are empty.
    """
    if isinstance(row, dict):
        row = pd.Series(row)
    blocks = runner_quality_blocks(row)
    active = [b for b in blocks.values() if not b.get("skipped")]
    if not active:
        return _legacy_runner_data_quality_pct(row)
    total_w = sum(int(b.get("weight") or 0) for b in active) or 100
    score = sum(int(b.get("pct") or 0) * int(b.get("weight") or 0) for b in active)
    return int(round(score / total_w))


def _legacy_runner_data_quality_pct(row: pd.Series | dict) -> int:
    """Original flat field checklist — kept for regression parity."""
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
    if _present(row.get("enrich_source")):
        checks.append(_first_present(row, "form_string", "horse_course_win_rate"))
    ok = 0
    for val in checks:
        if not _present(val):
            continue
        ok += 1
    return int(round(100 * ok / max(len(checks), 1)))
