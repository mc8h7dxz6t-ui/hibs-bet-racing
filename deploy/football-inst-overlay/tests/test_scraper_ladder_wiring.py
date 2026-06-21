"""Scraper ladder and scrape-first wiring tests."""

from __future__ import annotations


def test_fixture_fetch_flags_scrape_first(monkeypatch):
    from hibs_predictor.scrape_first import fixture_fetch_flags, scrape_first_mode

    monkeypatch.setenv("HIBS_DISABLE_API_SPORTS", "1")
    monkeypatch.delenv("API_SPORTS_FOOTBALL_KEY", raising=False)
    assert scrape_first_mode() is True
    prefer, skip = fixture_fetch_flags()
    assert prefer is True
    assert skip is True


def test_fpl_injury_hints_merged(monkeypatch):
    from hibs_predictor.team_news_enrich import apply_team_news_fields

    enriched = {
        "home": "Arsenal",
        "away": "Chelsea",
        "fixture_injuries": [],
        "supplemental": {
            "fpl_injury_hints": {
                "home": [{"player": "Saka", "chance_pct": 25, "news": "knock"}],
                "away": [],
            }
        },
    }
    apply_team_news_fields(enriched)
    assert enriched.get("injury_hint_source") == "fpl_availability"
    assert enriched["attack_availability_home"] < 1.0


def test_resolve_field_ft_result_delegates(monkeypatch):
    from hibs_predictor.scrapers import multi_scraper_api as msa

    monkeypatch.setattr(
        msa,
        "resolve_field",
        lambda field, row, clients, scrape_cache=None: (1, {"goals": {}}, "ok", "fotmob_calendar"),
    )
    fid, raw, note, src = msa.resolve_field("ft_result", object(), {})
    assert fid == 1
    assert src == "fotmob_calendar"


def test_fve_loader_peek_only_no_refresh(monkeypatch):
    pytest = __import__("pytest")
    pytest.importorskip("flask")
    from hibs_predictor.web import app

    calls = {"load": 0}

    def boom():
        calls["load"] += 1
        raise AssertionError("should not load full bundle")

    monkeypatch.setattr("hibs_predictor.web._load_fixtures_for_http", boom)
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user"] = "test"
    resp = client.get("/api/fve/lines/Missing%20Fixture")
    assert resp.status_code == 404
    assert calls["load"] == 0
