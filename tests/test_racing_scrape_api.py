"""Tests for racing Inst++ scrape API."""

from __future__ import annotations

from unittest.mock import patch


def test_scrape_first_status_shape():
    from hibs_racing.scrape_first import scrape_first_status

    st = scrape_first_status()
    assert "scrape_first" in st
    assert "reason" in st
    assert "default_cards_source" in st


def test_resolve_cards_source_auto(monkeypatch):
    monkeypatch.setenv("RACING_API_USERNAME", "u")
    monkeypatch.setenv("RACING_API_PASSWORD", "p")
    monkeypatch.delenv("HIBS_DISABLE_RACING_API", raising=False)
    from hibs_racing.scrapers.racing_scrape_api import resolve_cards_source

    assert resolve_cards_source("auto") == "racing_api"


def test_scrape_status_payload():
    from hibs_racing.scrapers.racing_scrape_api import scrape_status_payload

    payload = scrape_status_payload()
    assert payload["ok"] is True
    assert payload["product"] == "hibs-racing"
    assert "field_ladders" in payload
    assert "resilience" in payload


def test_racing_api_guard_status():
    from hibs_racing.racing_api_guard import status_payload

    st = status_payload()
    assert "traffic_allowed" in st
    assert "fallback_source" in st


@patch("hibs_racing.scrapers.racing_scrape_api.load_scored_cards")
def test_odds_coverage_summary(mock_load):
    import pandas as pd

    mock_load.return_value = pd.DataFrame(
        {"win_decimal": [2.5, None, 3.0], "runner_id": ["a", "b", "c"]}
    )
    from hibs_racing.scrapers.racing_scrape_api import odds_coverage_summary

    cov = odds_coverage_summary()
    assert cov["total"] == 3
    assert cov["priced"] == 2
