"""Tests for place probability reliability bins."""

from hibs_racing.analytics.reliability_bins import reliability_bins


def test_reliability_bins_well_calibrated():
    pairs = [(0.1, 0)] * 10 + [(0.9, 1)] * 10
    out = reliability_bins(pairs, n_bins=10, min_bin_n=5)
    assert out["n"] == 20
    assert out["brier"] is not None
    populated = [b for b in out["bins"] if not b.get("thin")]
    assert populated


def test_reliability_bins_empty():
    out = reliability_bins([])
    assert out["n"] == 0
    assert out["bins"] == []
