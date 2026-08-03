"""Racing GET /api/monetization/status."""

from __future__ import annotations


def test_racing_monetization_status_route():
    from hibs_racing.web import create_app

    app = create_app()
    client = app.test_client()
    resp = client.get("/api/monetization/status")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["schema"] == "hibs_monetization_status_v1"
    assert data["verticals"]["racing"] in ("affiliate", "paper", "micro", "live")
    assert "lanes" in data
