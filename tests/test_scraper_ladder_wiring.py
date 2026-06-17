"""Racing scraper ladder tests."""

from __future__ import annotations


def test_scrape_first_default_cards_source(monkeypatch):
    from hibs_racing.scrape_first import default_cards_source, scrape_first_mode

    monkeypatch.delenv("RACING_API_USERNAME", raising=False)
    monkeypatch.delenv("RACING_API_PASSWORD", raising=False)
    assert scrape_first_mode() is True
    assert default_cards_source() == "rpscrape"


def test_api_runner_rescue_flag():
    pytest = __import__("pytest")
    pytest.importorskip("flask")
    from hibs_racing.web import create_app

    client = create_app().test_client()
    resp = client.get("/api/runner/does-not-exist?rescue=1")
    assert resp.status_code == 404
