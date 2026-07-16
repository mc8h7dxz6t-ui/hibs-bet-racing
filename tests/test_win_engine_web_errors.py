"""Win-engine HTTP boundary — structured 404 without tracebacks."""

from __future__ import annotations

import json

import pytest

from hibs_racing.web import create_app


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("HIBS_WIN_ENGINE_ACTIVE", "0")
    db = tmp_path / "feature_store.sqlite"
    monkeypatch.setenv("HIBS_RACING_DB_PATH", str(db))
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_win_engine_predictions_inactive_structured_404(client):
    resp = client.get("/api/win-engine/predictions")
    assert resp.status_code == 404
    body = json.loads(resp.data)
    assert body["ok"] is False
    assert body["error"] in ("win_engine_inactive", "win_engine_unavailable")
    assert "Traceback" not in resp.get_data(as_text=True)
    assert "/opt/" not in resp.get_data(as_text=True)


def test_win_engine_unknown_route_structured_404(client):
    resp = client.get("/api/win-engine/does-not-exist")
    assert resp.status_code == 404
    body = json.loads(resp.data)
    assert body["ok"] is False
    assert "Traceback" not in resp.get_data(as_text=True)
