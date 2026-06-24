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
