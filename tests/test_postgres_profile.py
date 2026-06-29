"""Postgres production profile — Compliance ledger + Spend wallet."""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("INST_TEST_POSTGRES_DSN", "").strip(),
    reason="INST_TEST_POSTGRES_DSN not set",
)


@pytest.fixture
def pg_dsn() -> str:
    return os.environ["INST_TEST_POSTGRES_DSN"]


def test_postgres_compliance_ledger_append_and_verify(pg_dsn: str):
    from inst_spine.ledger_factory import open_ledger

    ledger = open_ledger(pg_dsn, writer_id="pg-test-compliance")
    entry = ledger.append(
        event_type="decision",
        payload={"snapshot": {"id": "t1"}, "outcome": {"status": "approved"}},
        manifest_id="pg-test-1",
    )
    assert entry.entry_id
    verify = ledger.verify()
    assert verify["chain_ok"] is True
    assert verify.get("backend") == "postgres"


def test_postgres_spend_wallet_reserve_settle(pg_dsn: str):
    from spend_guard.wallet_factory import open_wallet

    wallet = open_wallet(pg_dsn, initial_balance=500.0)
    ok, reason, hold_id = wallet.reserve(25.0, request_id="pg-soak-1")
    assert ok is True, reason
    assert hold_id
    ok2, reason2 = wallet.settle(hold_id, actual_amount=20.0)
    assert ok2 is True, reason2
    state = wallet.get_state()
    assert state.balance == 480.0
    assert state.locked is False
