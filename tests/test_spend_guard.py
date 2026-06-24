"""Tests for Spend Guard — reserve/settle wallet and drift lockout."""

from __future__ import annotations

from pathlib import Path

import pytest

from inst_spine.ledger import AppendOnlyLedger
from spend_guard.gateway import SpendGuardGateway, SpendRequest
from spend_guard.wallet import SpendWallet


def test_reserve_and_settle(tmp_path: Path):
    wallet_db = tmp_path / "wallet.sqlite"
    wallet = SpendWallet(wallet_db, initial_balance=100.0)
    ok, reason, hold_id = wallet.reserve(30.0, request_id="r1")
    assert ok and hold_id
    state = wallet.get_state()
    assert state.reserved == 30.0
    assert state.available == 70.0
    ok2, reason2 = wallet.settle(hold_id or "", actual_amount=25.0)
    assert ok2
    state2 = wallet.get_state()
    assert state2.balance == 75.0
    assert state2.reserved == 0.0


def test_duplicate_request_id_rejected(tmp_path: Path):
    wallet = SpendWallet(tmp_path / "w.sqlite", initial_balance=100.0)
    ok1, _, h1 = wallet.reserve(10.0, request_id="dup")
    ok2, reason2, _ = wallet.reserve(10.0, request_id="dup")
    assert ok1 and not ok2
    assert "duplicate" in reason2


def test_insufficient_balance(tmp_path: Path):
    wallet = SpendWallet(tmp_path / "w.sqlite", initial_balance=10.0)
    ok, reason, _ = wallet.reserve(50.0, request_id="r1")
    assert not ok
    assert "insufficient" in reason


def test_drift_lockout(tmp_path: Path):
    wallet = SpendWallet(
        tmp_path / "w.sqlite",
        initial_balance=1000.0,
        drift_threshold_pct=0.2,
        rolling_window=5,
    )
    for i in range(5):
        ok, _, hold = wallet.reserve(50.0, request_id=f"small-{i}")
        assert ok
        wallet.settle(hold or "", actual_amount=50.0)
    ok, _, hold = wallet.reserve(200.0, request_id="big-1")
    assert ok
    ok_settle, reason = wallet.settle(hold or "", actual_amount=200.0)
    state = wallet.get_state()
    assert state.locked or "DRIFT" in reason


def test_gateway_logs_to_ledger(tmp_path: Path):
    wallet_db = tmp_path / "wallet.sqlite"
    ledger_db = tmp_path / "ledger.sqlite"
    wallet = SpendWallet(wallet_db, initial_balance=500.0)
    ledger = AppendOnlyLedger(ledger_db)
    gw = SpendGuardGateway(wallet=wallet, ledger=ledger)
    r = gw.reserve(SpendRequest(request_id="g1", estimated_cost=10.0))
    assert r.decision.value == "approve"
    s = gw.settle(r.hold_id or "", actual_cost=9.0, request_id="g1")
    assert s.decision.value == "approve"
    assert any(e["event_type"] == "spend_guard" for e in ledger.list_entries())


def test_estimate_reserve_cost():
    from spend_guard.cost import actual_cost_from_usage, estimate_reserve_cost

    est, model = estimate_reserve_cost({"model": "gpt-4o-mini", "max_tokens": 100, "messages": [{"content": "hi"}]})
    assert est > 0
    assert model == "gpt-4o-mini"
    actual = actual_cost_from_usage({"prompt_tokens": 10, "completion_tokens": 5}, model="gpt-4o-mini")
    assert actual > 0


def test_spend_guard_serve_mock_chat(tmp_path: Path, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    import spend_guard.serve as serve_mod

    wallet_db = tmp_path / "wallet.sqlite"
    ledger_db = tmp_path / "ledger.sqlite"
    from spend_guard.wallet import SpendWallet

    SpendWallet(wallet_db, initial_balance=500.0)

    serve_mod.state.wallet_db = str(wallet_db)
    serve_mod.state.ledger_db = str(ledger_db)
    serve_mod.state.mock_upstream = True
    serve_mod.state.shadow_mode = False
    serve_mod.state.upstream_api_key = ""

    with TestClient(serve_mod.app) as client:
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["product"] == "spend-guard"

        body = {
            "model": "demo-model",
            "messages": [{"role": "user", "content": "hello"}],
            "max_tokens": 32,
        }
        r2 = client.post(
            "/v1/chat/completions",
            json=body,
            headers={"X-Request-Id": "http-test-1"},
        )
        assert r2.status_code == 200, r2.text
        data = r2.json()
        assert "choices" in data
        assert data["_spend_guard"]["request_id"] == "http-test-1"

        if serve_mod.state.ledger:
            serve_mod.state.ledger.stop_async_writer(flush=True)
        ledger = AppendOnlyLedger(ledger_db)
        assert any(e.get("event_type") == "spend_guard" for e in ledger.list_entries())


def test_spend_guard_serve_locked_wallet(tmp_path: Path, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    import spend_guard.serve as serve_mod
    from spend_guard.wallet import SpendWallet

    wallet_db = tmp_path / "wallet.sqlite"
    ledger_db = tmp_path / "ledger.sqlite"
    w = SpendWallet(wallet_db, initial_balance=100.0)
    w.lock("DRIFT_THRESHOLD_EXCEEDED: test")

    serve_mod.state.wallet_db = str(wallet_db)
    serve_mod.state.ledger_db = str(ledger_db)
    serve_mod.state.mock_upstream = True
    serve_mod.state.gateway = None

    with TestClient(serve_mod.app) as client:
        r = client.post(
            "/v1/chat/completions",
            json={"model": "demo-model", "messages": [{"role": "user", "content": "x"}]},
            headers={"X-Request-Id": "locked-1"},
        )
        assert r.status_code == 409
