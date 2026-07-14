"""Tests for racing field API and block-based data quality."""

from __future__ import annotations

import pandas as pd

from hibs_racing.cards.data_quality import runner_data_quality_pct, runner_quality_blocks
from hibs_racing.scrapers.multi_scraper_api import catalog_summary


def test_runner_quality_blocks_handicap():
    blocks = runner_quality_blocks(
        {
            "race_name": "Class 4 Handicap",
            "win_decimal": 5.0,
            "model_win_prob": 0.1,
            "model_place_prob": 0.3,
            "jockey": "A",
            "trainer": "B",
            "official_rating": 70,
            "card_comment": "held up",
        }
    )
    assert blocks["pricing"]["pct"] == 100
    assert blocks["handicap"]["pct"] == 100


def test_runner_quality_blocks_maiden_skips_handicap():
    row = {
        "race_name": "Maiden Stakes",
        "win_decimal": 5.0,
        "model_win_prob": 0.1,
        "model_place_prob": 0.3,
        "jockey": "A",
        "trainer": "B",
    }
    blocks = runner_quality_blocks(row)
    assert blocks["handicap"]["skipped"] is True
    assert runner_data_quality_pct(row) == 100


def test_racing_multi_scraper_catalog():
    cat = catalog_summary()
    assert cat["product"] == "hibs-racing"
    assert "win_odds" in cat["field_ladders"]
    ids = [x["id"] for x in cat["targeted_overflow"]]
    assert "matchbook" in ids


def test_api_runner_not_found():
    pytest = __import__("pytest")
    flask = pytest.importorskip("flask")
    del flask
    from hibs_racing.web import create_app

    client = create_app().test_client()
    resp = client.get("/api/runner/does-not-exist")
    assert resp.status_code == 404
    assert resp.get_json()["error"] == "runner_not_found"


def test_api_scrapers_catalog():
    pytest = __import__("pytest")
    pytest.importorskip("flask")
    from hibs_racing.web import create_app

    client = create_app().test_client()
    resp = client.get("/api/scrapers/catalog")
    assert resp.status_code == 200
    body = resp.get_json()
    assert "field_ladders" in body


def test_health_payload_includes_paper_and_cron():
    pytest = __import__("pytest")
    pytest.importorskip("flask")
    from hibs_racing.web import create_app

    client = create_app().test_client()
    resp = client.get("/api/health?full=1")
    assert resp.status_code == 200
    body = resp.get_json()
    assert "paper" in body
    assert "n_rows" in body["paper"]
    assert "cron" in body
    assert "card_fresh" in body or body.get("latest_card_date") is not None
    assert "execution" in body
    assert body["execution"].get("disabled") is True
