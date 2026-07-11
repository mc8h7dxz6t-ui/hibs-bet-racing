"""Single-instance VPC production envelope — /ready without scale profile."""

from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture
def single_instance_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Default single-tenant VPC — no INST_PRODUCTION_PROFILE, shadow where applicable."""
    monkeypatch.delenv("INST_PRODUCTION_PROFILE", raising=False)
    monkeypatch.delenv("INST_REDIS_URL", raising=False)
    monkeypatch.delenv("INST_REQUIRE_REDIS", raising=False)
    monkeypatch.delenv("INST_REQUIRE_POSTGRES", raising=False)
    monkeypatch.setenv("INST_FORCE_MEMORY_BACKENDS", "1")
    monkeypatch.setenv("PROXY_RISK_SHADOW", "1")
    monkeypatch.setenv("AD_GUARD_SHADOW", "1")
    db_root = tmp_path / "prod"
    db_root.mkdir()
    monkeypatch.setenv("PROXY_RISK_DATABASE", str(db_root / "proxy.sqlite"))
    monkeypatch.setenv("ALTDATA_LEDGER_DB", str(db_root / "altdata.sqlite"))
    monkeypatch.setenv("WEBHOOK_MESH_LEDGER", str(db_root / "webhook_mesh.sqlite"))
    monkeypatch.setenv("AD_GUARD_DATABASE", str(db_root / "ad_guard.sqlite"))
    monkeypatch.setenv("HEALTH_TELEMETRY_DB", str(db_root / "health.sqlite"))
    monkeypatch.setenv("SPEND_GUARD_WALLET_DB", str(db_root / "wallet.sqlite"))
    monkeypatch.setenv("SPEND_GUARD_LEDGER_DB", str(db_root / "spend.sqlite"))
    monkeypatch.setenv("AGENT_LEDGER_DB", str(db_root / "agent.sqlite"))
    monkeypatch.setenv("AGENT_LEDGER_PERMITS_DB", str(db_root / "permits.sqlite"))
    monkeypatch.setenv("WEBHOOK_PROVIDER_SECRET", "test-secret")
    monkeypatch.setenv("INST_WAL_PATH", str(db_root / "webhook.wal"))
    monkeypatch.setenv("WEBHOOK_DISPATCH_MODE", "background")
    yield db_root


def _seed_proxy(db: Path) -> None:
    from inst_spine.ledger import AppendOnlyLedger

    ledger = AppendOnlyLedger(db, writer_id="test")
    ledger.append(event_type="proxy_request", payload={"client_id": "seed"})


def _seed_altdata(db: Path) -> None:
    from altdata.poll import poll_once

    poll_once(
        feed_id="demo_feed",
        ctx={
            "demo_price": 1,
            "demo_seats": 1,
            "route_code": "X",
            "raw_html": "<td>1</td>",
        },
        database=db,
    )


def _seed_generic(db: Path, writer: str = "seed") -> None:
    from inst_spine.ledger import AppendOnlyLedger

    ledger = AppendOnlyLedger(db, writer_id=writer)
    ledger.append(event_type="seed", payload={"ok": True})


def _seed_spend(wallet_db: Path, ledger_db: Path) -> None:
    from spend_guard.wallet_factory import open_wallet

    if wallet_db.exists():
        wallet_db.unlink()
    open_wallet(wallet_db, initial_balance=1000.0)
    _seed_generic(ledger_db, "spend-guard")


def _seed_agent(ledger_db: Path) -> None:
    from agent_ledger.permits import PermitStore

    _seed_generic(ledger_db, "agent-ledger")
    permit_db = Path(os.environ["AGENT_LEDGER_PERMITS_DB"])
    PermitStore(permit_db)


@pytest.mark.parametrize(
    "module_path,ready_path,seed_fn,db_env",
    [
        ("proxy_risk.serve", "proxy", _seed_proxy, "PROXY_RISK_DATABASE"),
        ("altdata.serve", "altdata", _seed_altdata, "ALTDATA_LEDGER_DB"),
        ("webhook_mesh.serve", "webhook_mesh", lambda p: _seed_generic(p, "webhook-mesh"), "WEBHOOK_MESH_LEDGER"),
        ("ad_guard.serve", "ad_guard", lambda p: _seed_generic(p, "ad-guard"), "AD_GUARD_DATABASE"),
        ("health_telemetry.serve", "health", lambda p: _seed_generic(p, "health"), "HEALTH_TELEMETRY_DB"),
        ("spend_guard.serve", "spend", _seed_spend, ("SPEND_GUARD_WALLET_DB", "SPEND_GUARD_LEDGER_DB")),
        ("agent_ledger.serve", "agent", _seed_agent, ("AGENT_LEDGER_DB",)),
    ],
)
def test_sku_ready_single_instance(
    single_instance_env,
    module_path: str,
    ready_path: str,
    seed_fn,
    db_env,
):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    import importlib

    if isinstance(db_env, tuple):
        if module_path == "spend_guard.serve":
            wallet_db = Path(os.environ["SPEND_GUARD_WALLET_DB"])
            ledger_db = Path(os.environ["SPEND_GUARD_LEDGER_DB"])
            seed_fn(wallet_db, ledger_db)
        else:
            for key in db_env:
                seed_fn(Path(os.environ[key]))
    else:
        db = Path(os.environ[db_env])
        seed_fn(db)

    mod = importlib.import_module(module_path)
    with TestClient(mod.app) as client:
        r = client.get("/ready")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("ready") is True, body


def test_inst_workflow_ready_when_portfolio_seeded(single_instance_env, tmp_path: Path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from inst_workflow.demo_bootstrap import bootstrap_all

    demo_dir = tmp_path / "portfolio"
    os.environ["PORTFOLIO_DEMO_DIR"] = str(demo_dir)
    bootstrap_all(demo_dir=demo_dir, skip_live=True)

    import inst_workflow.serve as serve_mod

    serve_mod.state.demo_dir = demo_dir
    with TestClient(serve_mod.app) as client:
        r = client.get("/ready")
        assert r.status_code == 200
        assert r.json()["ready"] is True
