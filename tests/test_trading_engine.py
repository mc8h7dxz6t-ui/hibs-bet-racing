"""Tests for event-driven trading engine (stream cache + execution governor)."""

from __future__ import annotations

import threading
import time

import pytest

from hibs_racing.trading.delta_cache import MarketDeltaCache
from hibs_racing.trading.execution_governor import (
    ExecutionGovernor,
    IdempotencyGuard,
    build_order_payload,
    payload_signature,
)
from hibs_racing.trading.exchange_gateway import LiveExchangeWriteDisabled, dispatch_live_order
from hibs_racing.trading.store import ensure_trading_schema, get_wallet_state
from hibs_racing.features.store import connect


@pytest.fixture
def trading_db(tmp_path, monkeypatch):
    db = tmp_path / "feature_store.sqlite"
    monkeypatch.setenv("HIBS_RACING_DB_PATH", str(db))
    from hibs_racing.features.store import init_db

    init_db(db)
    return db


def test_delta_cache_thread_safe():
    cache = MarketDeltaCache()
    errors: list[str] = []

    def worker(i: int) -> None:
        try:
            for j in range(50):
                cache.apply_delta(
                    {
                        "market_id": "m1",
                        "runner_id": f"r{i}",
                        "back_odds": 2.0 + j * 0.01,
                        "ts_ms": int(time.time() * 1000),
                    }
                )
        except Exception as exc:
            errors.append(str(exc))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert cache.size() == 8


def test_idempotency_guard_rejects_within_window():
    guard = IdempotencyGuard(window_ms=5000)
    h = "abc123"
    assert guard.is_duplicate(h, now_ms=1000.0) is False
    assert guard.is_duplicate(h, now_ms=1500.0) is True
    assert guard.is_duplicate(h, now_ms=7000.0) is False


def test_governor_simulated_trade_when_live_disabled(trading_db, monkeypatch):
    monkeypatch.setenv("HIBS_LIVE_TRADING_ENABLED", "false")
    cache = MarketDeltaCache()
    cache.apply_delta(
        {"market_id": "100", "runner_id": "200", "back_odds": 5.0, "ts_ms": int(time.time() * 1000)}
    )
    gov = ExecutionGovernor(cache=cache, database=trading_db)
    payload = build_order_payload(market_id="100", runner_id="200", odds=5.0, stake=10.0)
    verdict = gov.dispatch(payload)
    assert verdict.allowed is True
    assert verdict.status == "SIMULATED"


def test_governor_slippage_reject(trading_db, monkeypatch):
    monkeypatch.setenv("HIBS_SLIPPAGE_MAX_TICKS", "1")
    monkeypatch.setenv("HIBS_TRADING_ODDS_TICK_SIZE", "0.1")
    cache = MarketDeltaCache()
    cache.apply_delta(
        {"market_id": "100", "runner_id": "200", "back_odds": 4.0, "ts_ms": int(time.time() * 1000)}
    )
    gov = ExecutionGovernor(cache=cache, database=trading_db)
    payload = build_order_payload(market_id="100", runner_id="200", odds=5.0, stake=5.0)
    verdict = gov.dispatch(payload)
    assert verdict.allowed is False
    assert verdict.status == "SLIPPAGE_REJECT"


def test_governor_latency_reject(trading_db, monkeypatch):
    monkeypatch.setenv("HIBS_EXECUTION_LATENCY_MAX_MS", "50")
    cache = MarketDeltaCache()
    gov = ExecutionGovernor(cache=cache, database=trading_db)
    payload = build_order_payload(market_id="100", runner_id="200", odds=5.0, stake=5.0)
    payload["created_at_ms"] = int(time.time() * 1000) - 500
    verdict = gov.dispatch(payload)
    assert verdict.allowed is False
    assert verdict.status == "LATENCY_REJECT"


def test_governor_cas_capital_reject(trading_db, monkeypatch):
    monkeypatch.setenv("HIBS_TRADING_WALLET_BALANCE", "100")
    with connect(trading_db) as conn:
        conn.execute(
            "UPDATE trading_wallet_state SET balance = 100, reserved = 0, version = 0 WHERE wallet_id = 'default'"
        )
        conn.commit()
    cache = MarketDeltaCache()
    cache.apply_delta(
        {"market_id": "100", "runner_id": "200", "back_odds": 5.0, "ts_ms": int(time.time() * 1000)}
    )
    gov = ExecutionGovernor(cache=cache, database=trading_db)
    payload = build_order_payload(market_id="100", runner_id="200", odds=5.0, stake=500.0)
    verdict = gov.dispatch(payload)
    assert verdict.allowed is False
    assert verdict.status == "CAPITAL_REJECT"


def test_live_exchange_stubbed_even_when_flag_true(monkeypatch):
    monkeypatch.setenv("HIBS_LIVE_TRADING_ENABLED", "true")
    with pytest.raises(LiveExchangeWriteDisabled):
        dispatch_live_order(
            {"market_id": "1", "runner_id": "2", "odds": 3.0, "stake": 1.0},
        )


def test_payload_signature_stable():
    a = {"stake": 1, "odds": 2.0, "market_id": "m", "runner_id": "r"}
    b = {"runner_id": "r", "market_id": "m", "odds": 2.0, "stake": 1}
    assert payload_signature(a) == payload_signature(b)


def test_stream_listener_parses_delta():
    from hibs_racing.trading.stream_listener import StreamListener

    listener = StreamListener()
    listener._handle_payload(
        {
            "type": "price_delta",
            "market_id": "55",
            "runner_id": "77",
            "back_odds": 6.5,
            "ts_ms": 1_700_000_000_000,
        }
    )
    tick = listener.cache.get("55", "77")
    assert tick is not None
    assert tick.back_odds == 6.5
    assert listener.stats.deltas_applied == 1


def test_wallet_cas_version_increments(trading_db):
    with connect(trading_db) as conn:
        before = get_wallet_state(conn)
        version = int(before["version"])
        from hibs_racing.trading.store import cas_reserve_capital

        ok, reason, new_version = cas_reserve_capital(
            conn, wallet_id="default", expected_version=version, stake=10.0
        )
        conn.commit()
    assert ok is True
    assert reason == "reserved"
    assert new_version == version + 1
