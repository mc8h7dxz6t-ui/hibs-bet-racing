"""Jinja display helpers for football dashboard templates."""

from __future__ import annotations

import math
from typing import Any


def normalize_prob_pct(value: Any) -> float | None:
    if value is None:
        return None
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(num) or math.isinf(num):
        return None
    if num <= 1.0:
        num *= 100.0
    while num > 100.0:
        num /= 100.0
    return round(max(0.0, min(100.0, num)), 1)


def fmt_num(value: Any, decimals: int = 2, suffix: str = "") -> str:
    if value is None:
        return "—"
    try:
        num = float(value)
    except (TypeError, ValueError):
        return "—"
    if math.isnan(num) or math.isinf(num):
        return "—"
    if decimals == 0:
        return f"{int(round(num))}{suffix}"
    return f"{num:.{decimals}f}{suffix}"


def fmt_pct(value: Any) -> str:
    num = normalize_prob_pct(value)
    if num is None:
        return "—"
    return f"{num:.0f}%"


def fmt_prob(value: Any, decimals: int = 1) -> str:
    """Format model probability percent (e.g. 42.3%)."""
    num = normalize_prob_pct(value)
    if num is None:
        return "—"
    if decimals <= 0:
        return f"{num:.0f}%"
    return f"{num:.{decimals}f}%"


def fmt_odds(value: Any, decimals: int = 2) -> str:
    """Format decimal odds for display."""
    return fmt_num(value, decimals)


def fmt_roi(value: Any, decimals: int = 1) -> str:
    """Format edge/ROI percent for value pills (e.g. +12.3%)."""
    if value is None:
        return "—"
    try:
        num = float(value)
    except (TypeError, ValueError):
        return "—"
    if math.isnan(num) or math.isinf(num):
        return "—"
    sign = "+" if num > 0 else ""
    return f"{sign}{num:.{decimals}f}%"
