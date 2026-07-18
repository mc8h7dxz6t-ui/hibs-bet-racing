"""A+ ops: unauthenticated mutating trading requests return 401."""

from __future__ import annotations

import json

import pytest

from hibs_racing.web import create_app


@pytest.fixture
def auth_client(tmp_path, monkeypatch):
    db = tmp_path / "feature_store.sqlite"
    monkeypatch.setenv("HIBS_RACING_DB_PATH", str(db))
    monkeypatch.setenv("HIBS_RACING_API_AUTH", "1")
    monkeypatch.setenv("HIBS_RACING_API_KEY", "test-secret-key-12345")
    monkeypatch.setattr(
        "hibs_racing.trading.status_plane.daemon_active",
        lambda **_: True,
    )
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def test_dispatch_without_api_key_returns_401(auth_client):
    resp = auth_client.post(
        "/api/trading/dispatch",
        data=json.dumps({"selection": "1", "odds": 3.0, "stake": 2.0}),
        content_type="application/json",
    )
    assert resp.status_code == 401
    body = resp.get_json()
    assert body.get("error") == "api_key_required"


def test_dispatch_with_bearer_key_succeeds(auth_client, monkeypatch):
    class _FakeGovernor:
        def __init__(self, **kwargs):
            pass

        def dispatch(self, payload):
            return type(
                "V",
                (),
                {
                    "to_dict": lambda _s: {"allowed": True, "status": "SIMULATED"},
                },
            )()

    monkeypatch.setattr(
        "hibs_racing.trading.execution_governor.ExecutionGovernor",
        _FakeGovernor,
    )
    resp = auth_client.post(
        "/api/trading/dispatch",
        data=json.dumps({"selection": "1", "odds": 3.0, "stake": 2.0}),
        content_type="application/json",
        headers={"Authorization": "Bearer test-secret-key-12345"},
    )
    assert resp.status_code == 200
    assert resp.get_json().get("ok") is True


def test_dispatch_rejects_when_daemon_inactive(auth_client, monkeypatch):
    monkeypatch.setattr(
        "hibs_racing.trading.status_plane.daemon_active",
        lambda **_: False,
    )
    resp = auth_client.post(
        "/api/trading/dispatch",
        data=json.dumps({"selection": "1", "odds": 3.0, "stake": 2.0}),
        content_type="application/json",
        headers={"Authorization": "Bearer test-secret-key-12345"},
    )
    assert resp.status_code == 503
    assert resp.get_json().get("error") == "trading_daemon_inactive"
