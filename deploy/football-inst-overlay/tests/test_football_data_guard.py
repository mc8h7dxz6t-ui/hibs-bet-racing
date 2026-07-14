"""Tests for Football-Data.org 403 guard."""

from __future__ import annotations


def test_auto_skip_paid_competitions(monkeypatch, tmp_path):
    monkeypatch.setenv("HIBS_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("HIBS_FOOTBALL_DATA_AUTO_SKIP_PAID", "1")
    from hibs_predictor.football_data_guard import competition_allowed, status_payload

    assert competition_allowed("WC") is False
    assert competition_allowed("WC") is False
    st = status_payload()
    assert "WC" in st["blocked_competitions"]


def test_competition_from_endpoint():
    from hibs_predictor.football_data_guard import competition_from_endpoint

    assert competition_from_endpoint("competitions/WC/standings") == "WC"
    assert competition_from_endpoint("competitions/PL/matches") == "PL"
