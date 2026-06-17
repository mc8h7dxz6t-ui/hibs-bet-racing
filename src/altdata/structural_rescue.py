"""Rung 4 structural rescue — offline HTML field extraction."""

from __future__ import annotations

import re
from typing import Any

# Per-target regex templates — version separately when DOM breaks
_RESCUE_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    "fare_price": [
        re.compile(r'"price"\s*:\s*([0-9]+\.?[0-9]*)', re.I),
        re.compile(r"data-price=['\"]([0-9.]+)", re.I),
        re.compile(r"£\s*([0-9]+\.?[0-9]*)"),
    ],
    "seat_count": [
        re.compile(r'"seats(?:Available)?"\s*:\s*([0-9]+)', re.I),
        re.compile(r"(\d+)\s+seats?\s+left", re.I),
    ],
    "route_code": [
        re.compile(r'"route(?:Code)?"\s*:\s*"([A-Z]{3}-[A-Z]{3})"', re.I),
        re.compile(r"([A-Z]{3})\s*[-→]\s*([A-Z]{3})"),
    ],
}


def structural_rescue(html: str, field: str) -> Any:
    """
    Lightweight local extractor — no LLM per row.
    Runs offline from poll hot path when ladder rungs 1–3 fail.
    """
    if not html:
        return None
    patterns = _RESCUE_PATTERNS.get(field, [])
    for pat in patterns:
        m = pat.search(html)
        if not m:
            continue
        if field == "route_code" and m.lastindex and m.lastindex >= 2:
            return f"{m.group(1)}-{m.group(2)}"
        return _coerce(field, m.group(1))
    return None


def _coerce(field: str, raw: str) -> Any:
    if field in ("fare_price",):
        try:
            return float(raw)
        except ValueError:
            return None
    if field in ("seat_count",):
        try:
            return int(raw)
        except ValueError:
            return None
    return raw
