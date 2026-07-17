"""Place picker environment configuration — strict tuple + type sanitization."""

from __future__ import annotations

import os
from typing import Callable, Tuple, TypeVar

T = TypeVar("T")


def _env_raw(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def _parse_tuple_value(raw: str, cast: Callable[[str], T], default: T) -> Tuple[T, ...]:
    text = (raw or "").strip()
    if not text:
        return (default,)
    if text.startswith("(") and text.endswith(")"):
        inner = text[1:-1].strip()
        if not inner:
            return (default,)
        parts = [part.strip() for part in inner.split(",") if part.strip()]
        if not parts:
            return (default,)
        return tuple(cast(part) for part in parts)
    return (cast(text),)


def _first_tuple_value(values: Tuple[T, ...], default: T) -> T:
    if not values:
        return default
    return values[0]


def _sanitize_float(name: str, default: float, *, low: float | None = None, high: float | None = None) -> float:
    values = _parse_tuple_value(_env_raw(name), float, default)
    val = float(_first_tuple_value(values, default))
    if low is not None:
        val = max(low, val)
    if high is not None:
        val = min(high, val)
    return val


def _sanitize_int(name: str, default: int, *, low: int | None = None) -> int:
    values = _parse_tuple_value(_env_raw(name), int, default)
    val = int(_first_tuple_value(values, default))
    if low is not None:
        val = max(low, val)
    return val


def place_henery_gamma_base() -> float:
    return _sanitize_float("HIBS_PLACE_HENERY_GAMMA_BASE", 0.88, low=0.05, high=2.0)


def min_place_edge_bps() -> int:
    return _sanitize_int("HIBS_PLACE_PICKER_MIN_EDGE_BPS", 250, low=0)


def liquidity_floor_gbp() -> float:
    return _sanitize_float("HIBS_PLACE_LIQUIDITY_FLOOR_GBP", 1500.0, low=0.0)


def config_snapshot() -> dict[str, float | int]:
    return {
        "henery_gamma_base": place_henery_gamma_base(),
        "min_place_edge_bps": min_place_edge_bps(),
        "liquidity_floor_gbp": liquidity_floor_gbp(),
    }
