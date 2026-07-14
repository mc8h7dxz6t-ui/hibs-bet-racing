"""Tests for place probability reliability bins."""

from hibs_racing.analytics.reliability_bins import (
    place_reliability_bins,
    settled_paper_calibration,
    win_reliability_bins,
)


def test_place_reliability_bins_well_calibrated():
    pairs = [(0.1, 0)] * 10 + [(0.9, 1)] * 10
    out = place_reliability_bins(pairs, n_bins=10, min_bin_n=5)
    assert out["n"] == 20
    assert out["brier"] is not None


def test_win_reliability_bins():
    rows = [{"model_win_prob": 0.2, "won": False}, {"model_win_prob": 0.8, "won": True}]
    bins = win_reliability_bins(rows, bins=5)
    assert bins


def test_settled_paper_calibration_empty(tmp_path, monkeypatch):
    db = tmp_path / "t.sqlite"
    monkeypatch.setenv("HIBS_RACING_DB_PATH", str(db))
    out = settled_paper_calibration(db)
    assert out["available"] is False
