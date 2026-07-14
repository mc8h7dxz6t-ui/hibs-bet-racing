"""API key and device auth middleware — Waves 1–2."""

from __future__ import annotations

import os

import pytest


@pytest.fixture
def agent_client(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    db = tmp_path / "agent.sqlite"
    permit = tmp_path / "permits.sqlite"
    monkeypatch.setenv("AGENT_LEDGER_DB", str(db))
    monkeypatch.setenv("AGENT_LEDGER_PERMITS_DB", str(permit))
    monkeypatch.setenv("AGENT_LEDGER_API_KEY", "test-agent-key")

    import agent_ledger.serve as mod

    with TestClient(mod.app) as client:
        yield client


def test_agent_ledger_requires_api_key(agent_client):
    r = agent_client.post(
        "/v1/authorize",
        json={"agent_id": "a1", "tool_name": "read_file", "arguments": {}},
    )
    assert r.status_code == 401

    r = agent_client.post(
        "/v1/authorize",
        json={"agent_id": "a1", "tool_name": "read_file", "arguments": {}},
        headers={"Authorization": "Bearer test-agent-key"},
    )
    assert r.status_code in (200, 403)
    assert agent_client.get("/ready").json()["ready"] is True


def test_spend_guard_requires_api_key(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    wallet = tmp_path / "w.sqlite"
    ledger = tmp_path / "l.sqlite"
    monkeypatch.setenv("SPEND_GUARD_WALLET_DB", str(wallet))
    monkeypatch.setenv("SPEND_GUARD_LEDGER_DB", str(ledger))
    monkeypatch.setenv("SPEND_GUARD_MOCK_UPSTREAM", "1")
    monkeypatch.setenv("SPEND_GUARD_API_KEY", "spend-test-key")

    import spend_guard.serve as mod

    mod.state.wallet_db = str(wallet)
    mod.state.ledger_db = str(ledger)
    mod.state.mock_upstream = True
    mod.state.gateway = None

    with TestClient(mod.app) as client:
        r = client.post("/v1/chat/completions", json={"model": "demo-model", "messages": []})
        assert r.status_code == 401
        r = client.post(
            "/v1/chat/completions",
            json={"model": "demo-model", "messages": [{"role": "user", "content": "hi"}]},
            headers={"Authorization": "Bearer spend-test-key", "X-Request-Id": "mw-1"},
        )
        assert r.status_code == 200
        assert client.get("/ready").json()["ready"] is True


def test_proxy_client_auth(monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    import hashlib
    import hmac

    from inst_spine.middleware import device_token_hmac, verify_device_token

    monkeypatch.setenv("PROXY_CLIENT_AUTH_SECRET", "proxy-secret")
    monkeypatch.setenv("PROXY_RISK_SHADOW", "1")
    monkeypatch.delenv("PROXY_RISK_API_KEY", raising=False)

    import proxy_risk.serve as mod

    mod.state.gateway = None
    mod.state.ledger = None

    sig = hmac.new(b"proxy-secret", b"client-a", hashlib.sha256).hexdigest()
    with TestClient(mod.app) as client:
        r = client.post(
            "/v1/evaluate",
            json={"client_id": "client-a", "method": "POST", "path": "/orders", "body": {}},
        )
        assert r.status_code == 401
        r = client.post(
            "/v1/evaluate",
            json={"client_id": "client-a", "method": "POST", "path": "/orders", "body": {}},
            headers={
                "X-Inst-Client-Id": "client-a",
                "X-Proxy-Client-Signature": sig,
            },
        )
        assert r.status_code == 200


def test_health_device_token(monkeypatch):
    from inst_spine.middleware import device_token_hmac, verify_device_token

    monkeypatch.setenv("HEALTH_DEVICE_AUTH_SECRET", "hospital-secret")
    token = device_token_hmac("ward-7", secret="hospital-secret")
    assert verify_device_token("ward-7", token)
    assert not verify_device_token("ward-7", "bad-token")


def test_health_ingress_device_auth(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    db = tmp_path / "health.sqlite"
    monkeypatch.setenv("HEALTH_TELEMETRY_DB", str(db))
    monkeypatch.setenv("HEALTH_DEVICE_AUTH_SECRET", "sec")
    monkeypatch.delenv("HEALTH_TELEMETRY_API_KEY", raising=False)

    from inst_spine.middleware import device_token_hmac

    import health_telemetry.serve as mod

    mod.state.ledger_db = db
    token = device_token_hmac("dev-1", secret="sec")
    pkt = {"ts": "2026-01-01T00:00:00Z", "seq": 1, "rpm": 72, "spo2": 98, "hr": 72}

    with TestClient(mod.app) as client:
        r = client.post(
            "/v1/telemetry/batch",
            json={"device_id": "dev-1", "packets": [pkt]},
            headers={"X-Device-Token": "wrong"},
        )
        assert r.status_code == 401
        r = client.post(
            "/v1/telemetry/batch",
            json={"device_id": "dev-1", "packets": [pkt], "batch_id": "b1"},
            headers={"X-Device-Token": token},
        )
        assert r.status_code == 200
