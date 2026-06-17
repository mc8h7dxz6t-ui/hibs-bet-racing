"""Tests for racing reliability bins analytics."""

from __future__ import annotations

from hibs_racing.analytics.reliability_bins import brier_score_win, reliability_bins


def test_reliability_bins_basic():
    rows = [
        {"model_win_prob": 0.15, "won": False},
        {"model_win_prob": 0.18, "won": True},
        {"model_win_prob": 0.55, "won": True},
        {"model_win_prob": 0.60, "won": False},
    ]
    bins = reliability_bins(rows, bins=5)
    assert bins
    assert sum(b["n"] for b in bins) == 4
    brier = brier_score_win(rows)
    assert brier is not None
    assert 0 <= brier <= 1
