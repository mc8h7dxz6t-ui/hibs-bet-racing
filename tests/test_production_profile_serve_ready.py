"""Production profile — fail-closed /ready across HTTP serves."""

from __future__ import annotations

import os

import pytest


@pytest.fixture
def prod_profile(monkeypatch):
    monkeypatch.setenv("INST_PRODUCTION_PROFILE", "1")
    monkeypatch.delenv("INST_FORCE_MEMORY_BACKENDS", raising=False)
    monkeypatch.delenv("INST_REDIS_URL", raising=False)
    monkeypatch.delenv("INST_POSTGRES_DSN", raising=False)


def _ready_not_ok(client) -> None:
    r = client.get("/ready")
    body = r.json()
    assert r.status_code in (200, 503)
    assert body.get("ready") is False


def test_compliance_ready_fail_closed_without_postgres(tmp_path, prod_profile, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    db = tmp_path / "compliance.sqlite"
    monkeypatch.setenv("COMPLIANCE_LOGGER_DATABASE", str(db))
    monkeypatch.setenv("COMPLIANCE_LOGGER_API_KEY", "prod-compliance-key")

    import compliance_log.serve as mod

    mod.state.database = str(db)
    with TestClient(mod.app) as client:
        _ready_not_ok(client)
        r = client.post("/v1/decisions", json={"snapshot": {"id": "1"}, "outcome": {"ok": True}})
        assert r.status_code == 401
        r2 = client.post(
            "/v1/decisions",
            json={"snapshot": {"id": "1"}, "outcome": {"ok": True}},
            headers={"Authorization": "Bearer prod-compliance-key"},
        )
        assert r2.status_code in (200, 422, 503)


def test_webhook_mesh_ready_blocks_background_dispatch(prod_profile, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    monkeypatch.setenv("WEBHOOK_PROVIDER_SECRET", "prod-secret")
    monkeypatch.setenv("WEBHOOK_DISPATCH_MODE", "background")

    import webhook_mesh.serve as mod

    with TestClient(mod.app) as client:
        _ready_not_ok(client)


def test_proxy_risk_ready_requires_redis_in_prod(tmp_path, prod_profile, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    db = tmp_path / "proxy.sqlite"
    monkeypatch.setenv("PROXY_RISK_DATABASE", str(db))
    monkeypatch.setenv("PROXY_RISK_SHADOW", "0")

    import proxy_risk.serve as mod

    mod.state.database = str(db)
    mod.state.shadow_mode = False
    with TestClient(mod.app) as client:
        _ready_not_ok(client)


def test_spend_guard_ready_requires_ha_backends(tmp_path, prod_profile, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    wallet = tmp_path / "wallet.sqlite"
    ledger = tmp_path / "ledger.sqlite"
    monkeypatch.setenv("SPEND_GUARD_WALLET_DB", str(wallet))
    monkeypatch.setenv("SPEND_GUARD_LEDGER_DB", str(ledger))
    monkeypatch.setenv("SPEND_GUARD_MOCK_UPSTREAM", "1")
    monkeypatch.setenv("SPEND_GUARD_API_KEY", "prod-spend-key")

    import spend_guard.serve as mod

    mod.state.wallet_db = str(wallet)
    mod.state.ledger_db = str(ledger)
    mod.state.mock_upstream = True
    mod.state.gateway = None
    with TestClient(mod.app) as client:
        _ready_not_ok(client)
        r = client.post("/v1/chat/completions", json={"model": "m", "messages": []})
        assert r.status_code == 401


def test_agent_ledger_ready_requires_redis(tmp_path, prod_profile, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    db = tmp_path / "agent.sqlite"
    permit = tmp_path / "permits.sqlite"
    monkeypatch.setenv("AGENT_LEDGER_DB", str(db))
    monkeypatch.setenv("AGENT_LEDGER_PERMITS_DB", str(permit))
    monkeypatch.setenv("AGENT_LEDGER_API_KEY", "prod-agent-key")

    import agent_ledger.serve as mod

    with TestClient(mod.app) as client:
        _ready_not_ok(client)
