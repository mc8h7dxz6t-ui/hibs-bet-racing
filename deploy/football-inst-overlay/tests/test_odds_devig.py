"""Odds de-vig helpers."""

from __future__ import annotations

from hibs_predictor.odds_devig import (
    fair_probs_from_odds,
    log_odds_alpha,
    odds_ratio_devig_probs,
    shin_devig_probs,
)


def test_odds_ratio_sums_to_one():
    odds = {"home": 2.0, "draw": 3.5, "away": 4.0}
    probs = odds_ratio_devig_probs(odds)
    assert abs(sum(probs.values()) - 1.0) < 1e-6


def test_shin_devig_sums_to_one():
    odds = {"home": 1.95, "draw": 3.5, "away": 4.0}
    probs = shin_devig_probs(odds)
    assert abs(sum(probs.values()) - 1.0) < 1e-6


def test_fair_probs_shin():
    odds = {"home": 2.0, "draw": 3.4, "away": 3.8}
    fair = fair_probs_from_odds(odds, method="shin")
    assert fair["home"] > 0


def test_log_odds_alpha_positive_edge():
    alpha = log_odds_alpha(0.55, 0.45)
    assert alpha is not None
    assert alpha > 0
