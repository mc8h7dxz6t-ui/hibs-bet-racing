from __future__ import annotations

import math
from typing import Any


def normalize_prob_pct(value: Any) -> float | None:
    """Map a probability to 0–100 display scale (handles 0–1 or double-scaled inputs)."""
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


def fmt_prob_phrase(value: Any, *, decimals: int = 0) -> str:
    """Short percentage for pick reasoning sentences."""
    num = normalize_prob_pct(value)
    if num is None:
        return "—"
    if decimals <= 0:
        return f"{num:.0f}%"
    return f"{num:.{decimals}f}%"


def json_safe(value: Any) -> Any:
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_safe(v) for v in value]
    return value
