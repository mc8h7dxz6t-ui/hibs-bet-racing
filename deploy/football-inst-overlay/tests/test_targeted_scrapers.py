"""Tests for FPL and ESPN targeted scraper clients."""

from __future__ import annotations

from datetime import date


def test_fpl_team_season_xg_profile(monkeypatch):
    from hibs_predictor.scrapers import fpl_client as fpl

    monkeypatch.setenv("HIBS_ENABLE_FPL_EPL", "1")
    bootstrap = {
        "teams": [{"id": 1, "name": "Arsenal", "short_name": "ARS"}],
        "elements": [
            {
                "team": 1,
                "element_type": 3,
                "expected_goals": "2.0",
                "minutes": 900,
            },
            {
                "team": 1,
                "element_type": 3,
                "expected_goals": "1.5",
                "minutes": 800,
            },
            {
                "team": 1,
                "element_type": 1,
                "expected_goals": "0.0",
                "expected_goals_conceded": "10.0",
                "minutes": 900,
            },
        ],
    }
    fixtures = [
        {"team_h": 1, "team_a": 2, "team_h_score": 2, "team_a_score": 0, "finished": True},
        {"team_h": 3, "team_a": 1, "team_h_score": 1, "team_a_score": 1, "finished": True},
    ]

    monkeypatch.setattr(fpl, "fetch_bootstrap", lambda **kw: bootstrap)
    monkeypatch.setattr(fpl, "fetch_fixtures", lambda **kw: fixtures)

    prof = fpl.team_season_xg_profile("Arsenal")
    assert prof is not None
    assert prof["avg_xg_for"] > 0
    assert prof["avg_xg_against"] > 0
    assert prof["source"] == "fpl_api"


def test_espn_event_to_fixture_format_scheduled():
    from hibs_predictor.scrapers.espn_client import event_to_fixture_format

    event = {
        "id": "401547403",
        "date": "2026-06-21T19:00Z",
        "status": {"type": {"name": "STATUS_SCHEDULED", "state": "pre"}},
        "competitions": [
            {
                "competitors": [
                    {"homeAway": "home", "score": "0", "team": {"id": 1, "displayName": "France"}},
                    {"homeAway": "away", "score": "0", "team": {"id": 2, "displayName": "Senegal"}},
                ]
            }
        ],
    }
    row = event_to_fixture_format(event, "WORLD_CUP")
    assert row is not None
    assert row["source"] == "espn_scoreboard"
    assert row["fixture"]["status"]["short"] == "NS"
    assert row["teams"]["home"]["name"] == "France"


def test_espn_fixtures_enabled_scrape_first(monkeypatch):
    from hibs_predictor.scrapers.espn_client import espn_fixtures_enabled

    monkeypatch.setenv("HIBS_DISABLE_API_SPORTS", "1")
    monkeypatch.delenv("HIBS_ENABLE_ESPN_FIXTURES", raising=False)
    assert espn_fixtures_enabled() is True
    monkeypatch.setenv("HIBS_ENABLE_ESPN_FIXTURES", "0")
    assert espn_fixtures_enabled() is False


def test_espn_event_to_recent_format():
    from hibs_predictor.scrapers.espn_client import event_to_recent_format

    event = {
        "id": "1",
        "date": "2026-06-16T19:00Z",
        "status": {"type": {"name": "STATUS_FULL_TIME", "completed": True, "state": "post"}},
        "competitions": [
            {
                "competitors": [
                    {"homeAway": "home", "score": "3", "team": {"displayName": "France"}},
                    {"homeAway": "away", "score": "1", "team": {"displayName": "Senegal"}},
                ]
            }
        ],
    }
    row = event_to_recent_format(event)
    assert row is not None
    assert row["goals"] == {"home": 3, "away": 1}


def test_scraped_xg_fpl_resolver(monkeypatch):
    from hibs_predictor.scraped_xg import resolve_scraped_xg

    monkeypatch.setenv("HIBS_SCRAPE_XG", "1")
    monkeypatch.setenv("HIBS_ENABLE_FPL_EPL", "1")
    monkeypatch.setenv("HIBS_ENABLE_UNDERSTAT_LIGHT", "0")
    monkeypatch.setenv("HIBS_ENABLE_FOTMOB_XG", "0")
    monkeypatch.setattr("hibs_predictor.scraped_xg._fetch_understat_row", lambda *a, **k: None)

    def fake_profile(name):
        if name == "Arsenal":
            return {"avg_xg_for": 1.8, "avg_xg_against": 0.9, "n": 10}
        if name == "Chelsea":
            return {"avg_xg_for": 1.5, "avg_xg_against": 1.1, "n": 10}
        return None

    monkeypatch.setattr(
        "hibs_predictor.scrapers.fpl_client.team_season_xg_profile",
        fake_profile,
    )

    fixture = {"home": "Arsenal", "away": "Chelsea"}
    enriched = {"xg_source": "goals_proxy", "home_xg": 1.0, "away_xg": 1.0}
    hit = resolve_scraped_xg(fixture, "EPL", enriched)
    assert hit is not None
    assert hit[2] == "fpl_api_xg"
    assert hit[0] > 1.0


def test_multi_scraper_catalog():
    from hibs_predictor.scrapers.multi_scraper_api import catalog_summary

    cat = catalog_summary()
    assert "ft_result" in cat["field_ladders"]
    ids = [x["id"] for x in cat["targeted_overflow"]]
    assert "espn_scoreboard" in ids
    assert "fpl_api" in ids
