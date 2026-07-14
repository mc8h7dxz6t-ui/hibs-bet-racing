"""Tests for scrape-only low-source HTTP API."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def test_scrape_status_payload():
    from hibs_predictor.scrapers.low_source_api import scrape_status_payload

    payload = scrape_status_payload()
    assert payload["ok"] is True
    assert payload["mode"] == "scrape_only"
    assert "ft_result" in payload["field_ladders"]
    assert payload["wired_source_count"] >= 5


def test_fixture_key_and_match():
    from hibs_predictor.scrapers.low_source_api import (
        find_fixture_in_rows,
        fixture_key,
        fixture_label,
    )

    row = {
        "home": {"name": "Arsenal"},
        "away": {"name": "Chelsea"},
        "date": "2026-06-21T15:00:00+00:00",
    }
    key = fixture_key(row)
    assert key == "Arsenal|Chelsea|2026-06-21T15:00:00+00:00"
    assert fixture_label("Arsenal", "Chelsea") == "Arsenal v Chelsea"
    assert find_fixture_in_rows([row], "Arsenal v Chelsea") is row
    assert find_fixture_in_rows([row], key) is row


@patch("hibs_predictor.scrapers.low_source_api.fetch_scrape_only_fixtures")
def test_resolve_fixture_low_source(mock_fetch):
    from hibs_predictor.scrapers.low_source_api import resolve_fixture_low_source

    fixture = {
        "home": {"id": 1, "name": "France"},
        "away": {"id": 2, "name": "Senegal"},
        "date": "2026-06-21T19:00:00+00:00",
        "source": "espn_scoreboard",
        "fixture": {"id": "espn_1", "status": {"short": "NS"}},
    }
    mock_fetch.return_value = [fixture]
    agg = MagicMock()
    agg.enrich_fixture.return_value = {
        **fixture,
        "home_recent_n": 2,
        "away_recent_n": 1,
        "xg_home": 1.4,
        "xg_away": 1.1,
        "xg_source": "goals_proxy",
        "home_stats": {},
        "away_stats": {},
        "home_position": {},
        "away_position": {},
    }
    with patch(
        "hibs_predictor.data_quality.compute_fixture_data_quality",
        return_value={"score_pct": 42.0, "blocks": []},
    ):
        payload = resolve_fixture_low_source("France v Senegal", "WORLD_CUP", agg, rescue=True)
    assert payload is not None
    assert payload["ok"] is True
    assert payload["rescued"] is True
    assert payload["thin_data"] is True
    assert payload["data_quality_pct"] == 42.0
    assert "espn_scoreboard" in payload["sources_used"]


@patch("hibs_predictor.scrapers.low_source_api.maybe_backfill_fixture_bundle")
@patch("hibs_predictor.scrapers.low_source_api.enrich_low_source")
@patch("hibs_predictor.scrapers.low_source_api.fetch_scrape_only_fixtures")
@patch("hibs_predictor.scrapers.low_source_api._low_source_league_codes", return_value=["EPL"])
def test_run_low_source_scrape_cycle(mock_leagues, mock_fetch, mock_enrich, mock_backfill):
    from hibs_predictor.scrapers.low_source_api import run_low_source_scrape_cycle

    fixture = {"home": {"name": "A"}, "away": {"name": "B"}, "date": "2026-06-21T15:00:00+00:00"}
    mock_fetch.return_value = [fixture]
    mock_enrich.return_value = {**fixture, "data_quality": {"score_pct": 55.0}}
    mock_backfill.return_value = {"backfilled": True, "merged": 1, "bundle_count": 1}
    agg = MagicMock()
    report = run_low_source_scrape_cycle(agg, force=True)
    assert report["fixture_count"] == 1
    assert report["enriched_count"] == 1
    assert report["backfill"]["backfilled"] is True


def test_api_scrape_routes_smoke():
    pytest = __import__("pytest")
    pytest.importorskip("flask")
    from hibs_predictor.web import app

    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user"] = "test"

    status = client.get("/api/scrape/status")
    assert status.status_code == 200
    body = status.get_json()
    assert body["ok"] is True
    assert "field_ladders" in body

    with patch(
        "hibs_predictor.scrapers.low_source_api.fetch_scrape_only_fixtures",
        return_value=[],
    ):
        fixtures = client.get("/api/scrape/fixtures?league=EPL")
    assert fixtures.status_code == 200
    assert fixtures.get_json()["count"] == 0

    missing = client.get("/api/scrape/fixture/No%20Match%20v%20Here?league=EPL")
    assert missing.status_code == 404
    assert missing.get_json()["error"] == "fixture_not_found"
