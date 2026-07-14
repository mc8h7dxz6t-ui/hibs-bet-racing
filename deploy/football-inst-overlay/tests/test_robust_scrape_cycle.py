"""Tests for robust odds scrape and scrape cycle."""

from __future__ import annotations

from unittest.mock import MagicMock


def test_odds_coverage_summary():
    from hibs_predictor.scrapers.robust_odds_scrape import odds_coverage_summary

    rows = [
        {"odds_available": True, "odds_primary_source": "the_odds_api"},
        {"odds_available": False, "odds_home": None},
    ]
    cov = odds_coverage_summary(rows)
    assert cov["total"] == 2
    assert cov["with_odds"] == 1
    assert cov["coverage_pct"] == 50.0


def test_run_odds_rescue_pass_skips_complete(monkeypatch):
    from hibs_predictor.scrapers.robust_odds_scrape import run_odds_rescue_pass

    rows = [{"odds_available": True, "league": "EPL"}]
    agg = MagicMock()
    report = run_odds_rescue_pass(agg, rows)
    assert report["rescued"] == 0
    assert report["coverage"]["with_odds"] == 1


def test_robust_scrape_slo_no_report():
    from hibs_predictor.scrapers.robust_scrape_cycle import robust_scrape_slo_status

    st = robust_scrape_slo_status()
    assert "ok" in st
    assert "message" in st
