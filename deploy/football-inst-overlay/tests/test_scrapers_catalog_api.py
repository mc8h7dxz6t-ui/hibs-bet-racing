"""Catalog API smoke test for football multi-scraper registry."""

from __future__ import annotations


def test_api_scrapers_catalog_route():
    pytest = __import__("pytest")
    pytest.importorskip("flask")
    from hibs_predictor.web import app

    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user"] = "test"
    resp = client.get("/api/scrapers/catalog")
    assert resp.status_code == 200
    body = resp.get_json()
    assert "ft_result" in body["field_ladders"]
    assert "team_xg" in body["field_ladders"]
