"""Each-way Kelly — win + place leg fractional Kelly (not exchange place math)."""

from __future__ import annotations

from hibs_racing.place.ew_ev import EachWayQuote, each_way_ev


def _leg_kelly(p: float, decimal_odds: float) -> float:
    if decimal_odds <= 1.0 or p <= 0.0 or p >= 1.0:
        return 0.0
    b = decimal_odds - 1.0
    if b <= 0.0:
        return 0.0
    q = 1.0 - p
    raw = (p * b - q) / b
    return max(0.0, raw)


def each_way_kelly_fraction(
    model_win_prob: float,
    model_place_prob: float,
    quote: EachWayQuote,
    *,
    kelly_fraction: float = 0.25,
    max_runner_risk_pct: float = 0.02,
) -> float:
    """
    Fractional Kelly for standard each-way (50/50 win + place stakes).

    Uses separate win/place leg Kelly on half-stakes, summed — not exchange place Kelly.
    """
    ev = each_way_ev(model_win_prob, model_place_prob, quote)
    if ev.combined_ev <= 0:
        return 0.0

    offered_place = 1.0 + (quote.win_decimal - 1.0) * quote.place_fraction
    k_win = _leg_kelly(model_win_prob, quote.win_decimal) * 0.5
    k_place = _leg_kelly(model_place_prob, offered_place) * 0.5
    raw = (k_win + k_place) * kelly_fraction
    return min(max(0.0, raw), max_runner_risk_pct)
