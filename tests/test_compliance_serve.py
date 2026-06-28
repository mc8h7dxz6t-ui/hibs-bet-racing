"""Compliance Logger HTTP serve tests."""

from __future__ import annotations

from pathlib import Path

import pytest


def test_compliance_serve_ingest_and_ready(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    db = tmp_path / "compliance.sqlite"
    monkeypatch.setenv("COMPLIANCE_LOGGER_DATABASE", str(db))
    monkeypatch.delenv("COMPLIANCE_LOGGER_API_KEY", raising=False)

    import compliance_log.serve as serve_mod

    serve_mod.state.database = str(db)

    with TestClient(serve_mod.app) as client:
        assert client.get("/health").json()["ok"] is True
        assert client.get("/ready").json()["ready"] is True
        r = client.post(
            "/v1/decisions",
            json={
                "snapshot": {"id": "s1", "status": "ok"},
                "outcome": {"approved": True},
                "actor": "http-test",
            },
        )
        assert r.status_code == 200
        assert r.json()["ok"] is True
        assert client.get("/ready").json()["ready"] is True


def test_compliance_serve_requires_api_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    monkeypatch.setenv("COMPLIANCE_LOGGER_DATABASE", str(tmp_path / "c.sqlite"))
    monkeypatch.setenv("COMPLIANCE_LOGGER_API_KEY", "compliance-key")

    import compliance_log.serve as serve_mod

    serve_mod.state.database = str(tmp_path / "c.sqlite")

    with TestClient(serve_mod.app) as client:
        r = client.post("/v1/decisions", json={"snapshot": {}, "outcome": {}})
        assert r.status_code == 401
        r2 = client.post(
            "/v1/decisions",
            json={"snapshot": {"id": "1"}, "outcome": {"ok": True}},
            headers={"Authorization": "Bearer compliance-key"},
        )
        assert r2.status_code == 422 or r2.status_code == 200
