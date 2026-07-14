"""API key auth for mutating hibs-racing routes."""

from __future__ import annotations

import importlib

import pytest


def _reload_app(monkeypatch, **env):
    for key, value in env.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)
    import hibs_racing.middleware.auth as auth_mod
    import hibs_racing.web as web_mod

    importlib.reload(auth_mod)
    web = importlib.reload(web_mod)
    return web


def _auth_headers(key: str = "test-racing-key") -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


def test_mutating_routes_public_when_auth_disabled(monkeypatch):
    web = _reload_app(
        monkeypatch,
        HIBS_RACING_API_AUTH="0",
        HIBS_RACING_PRODUCTION="0",
        HIBS_RACING_API_KEY=None,
    )
    client = web.create_app().test_client()
    assert client.post("/api/settle-paper").status_code != 401
    assert client.get("/api/settings/monetization").status_code != 401


def test_mutating_routes_require_key_when_auth_enabled(monkeypatch):
    web = _reload_app(
        monkeypatch,
        HIBS_RACING_API_AUTH="1",
        HIBS_RACING_API_KEY="test-racing-key",
        HIBS_RACING_PRODUCTION="0",
    )
    client = web.create_app().test_client()
    denied = client.post("/api/settle-paper")
    assert denied.status_code == 401
    assert denied.get_json()["error"] == "api_key_required"
    ok = client.post("/api/settle-paper", headers=_auth_headers())
    assert ok.status_code != 401


def test_settings_get_public_post_protected(monkeypatch):
    web = _reload_app(
        monkeypatch,
        HIBS_RACING_API_AUTH="1",
        HIBS_RACING_API_KEY="test-racing-key",
        HIBS_RACING_PRODUCTION="0",
    )
    client = web.create_app().test_client()
    assert client.get("/api/settings/monetization").status_code != 401
    denied = client.post("/api/settings/monetization", json={})
    assert denied.status_code == 401
    ok = client.post("/api/settings/monetization", json={}, headers=_auth_headers())
    assert ok.status_code != 401


def test_production_auto_auth_when_key_set(monkeypatch):
    web = _reload_app(
        monkeypatch,
        HIBS_RACING_API_AUTH=None,
        HIBS_RACING_PRODUCTION="on",
        HIBS_RACING_API_KEY="prod-key",
    )
    client = web.create_app().test_client()
    assert client.post("/api/refresh").status_code == 401
    ok = client.post("/api/refresh", headers={"X-Hibs-Api-Key": "prod-key"})
    assert ok.status_code != 401


def test_validate_auth_config_requires_key(monkeypatch):
    monkeypatch.setenv("HIBS_RACING_API_AUTH", "1")
    monkeypatch.delenv("HIBS_RACING_API_KEY", raising=False)
    from hibs_racing.middleware.auth import validate_auth_config

    with pytest.raises(RuntimeError, match="HIBS_RACING_API_KEY"):
        validate_auth_config()
