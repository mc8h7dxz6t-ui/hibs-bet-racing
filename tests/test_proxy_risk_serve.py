"""Proxy-Risk production HTTP serve tests."""

from __future__ import annotations

from pathlib import Path

import pytest


def test_proxy_risk_serve_evaluate_shadow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    import proxy_risk.serve as serve_mod

    db = tmp_path / "proxy.sqlite"
    monkeypatch.delenv("PROXY_RISK_API_KEY", raising=False)
    monkeypatch.delenv("PROXY_RISK_API_TOKEN", raising=False)
    monkeypatch.setenv("INST_FORCE_MEMORY_BACKENDS", "1")
    serve_mod.state.ledger_db = str(db)
    serve_mod.state.shadow_mode = True
    serve_mod.state.gateway = None
    serve_mod.state.ledger = None

    with TestClient(serve_mod.app) as client:
        assert client.get("/health").json()["ok"] is True
        ready = client.get("/ready")
        assert ready.status_code == 200
        assert ready.json()["ready"] is True

        r = client.post(
            "/v1/evaluate",
            json={
                "client_id": "serve-test",
                "method": "POST",
                "path": "/orders",
                "body": {"symbol": "AAPL", "qty": 1},
                "idempotency_key": "serve-key-1",
            },
        )
        assert r.status_code == 200
        assert r.json()["decision"] == "approve"
        assert r.json()["ok"] is True

        dup = client.post(
            "/v1/evaluate",
            json={
                "client_id": "serve-test",
                "method": "POST",
                "path": "/orders",
                "body": {"symbol": "AAPL", "qty": 1},
                "idempotency_key": "serve-key-1",
            },
        )
        assert dup.status_code == 429
        assert dup.json()["decision"] == "reject"


def test_proxy_risk_serve_requires_api_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    import proxy_risk.serve as serve_mod

    monkeypatch.setenv("PROXY_RISK_API_KEY", "proxy-test-key")
    serve_mod.state.ledger_db = str(tmp_path / "proxy_auth.sqlite")
    serve_mod.state.gateway = None
    serve_mod.state.ledger = None

    with TestClient(serve_mod.app) as client:
        r = client.post("/v1/evaluate", json={"client_id": "x", "path": "/", "body": {}})
        assert r.status_code == 401
        r2 = client.post(
            "/v1/evaluate",
            json={"client_id": "x", "path": "/", "body": {}},
            headers={"Authorization": "Bearer proxy-test-key"},
        )
        assert r2.status_code == 200
