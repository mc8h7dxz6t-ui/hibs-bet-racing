from __future__ import annotations

from dataclasses import dataclass


@dataclass
class EachWayQuote:
    win_decimal: float
    place_fraction: float  # e.g. 0.25 for 1/4
    places: int = 3


@dataclass
class EachWayEV:
    win_ev: float
    place_ev: float
    combined_ev: float
    model_win_prob: float
    model_place_prob: float
    offered_place_decimal: float


def exchange_place_ev(
    model_place_prob: float,
    place_decimal: float,
    *,
    commission: float = 0.02,
) -> float:
    """
    Pure £1 place-bet EV vs exchange back price (commission on net winnings).
    Returns NaN when inputs are invalid.
    """
    if place_decimal <= 1.0 or model_place_prob < 0.0 or model_place_prob > 1.0:
        return float("nan")
    net_return = 1.0 + (place_decimal - 1.0) * (1.0 - commission)
    return model_place_prob * (net_return - 1.0) - (1.0 - model_place_prob)


def each_way_ev(
    model_win_prob: float,
    model_place_prob: float,
    quote: EachWayQuote,
    *,
    stake: float = 1.0,
) -> EachWayEV:
    """
    Each-way EV vs book place terms (fixed fraction of win odds).
    stake split 50/50 win + place on a standard EW bet.
    """
    win_stake = stake * 0.5
    place_stake = stake * 0.5

    offered_place = 1.0 + (quote.win_decimal - 1.0) * quote.place_fraction
    win_ev = win_stake * (model_win_prob * quote.win_decimal - 1.0)
    place_ev = place_stake * (model_place_prob * offered_place - 1.0)
    return EachWayEV(
        win_ev=win_ev,
        place_ev=place_ev,
        combined_ev=win_ev + place_ev,
        model_win_prob=model_win_prob,
        model_place_prob=model_place_prob,
        offered_place_decimal=offered_place,
    )
