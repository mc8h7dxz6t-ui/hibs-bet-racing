"""Fractional Kelly for pure exchange place bets."""

from __future__ import annotations


def place_kelly_fraction(
    p_place: float,
    place_decimal: float,
    *,
    commission: float = 0.02,
    kelly_fraction: float = 0.25,
    max_runner_risk_pct: float = 0.02,
) -> float:
    """Suggested bankroll fraction (0–max_runner_risk_pct) for a place back."""
    if place_decimal <= 1.0 or p_place <= 0.0 or p_place >= 1.0:
        return 0.0
    o_net = (place_decimal - 1.0) * (1.0 - commission)
    if o_net <= 0.0:
        return 0.0
    q = 1.0 - p_place
    raw = (p_place * o_net - q) / o_net
    if raw <= 0.0:
        return 0.0
    return min(raw * kelly_fraction, max_runner_risk_pct)
