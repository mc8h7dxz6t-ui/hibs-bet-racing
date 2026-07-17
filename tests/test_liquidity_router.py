"""Tests for liquidity router (simulation only)."""

from __future__ import annotations

import json
import time

import pytest

from hibs_racing.trading.config import liquidity_router_active
from hibs_racing.trading.delta_cache import MarketDeltaCache
from hibs_racing.trading.liquidity_router import (
    DISARMED_BY_ADVERSE_SELECTION,
    LiquidityRouter,
    adverse_selection_abort,
    flight_latency_ms,
    hedge_delta_bps,
    lay_stake_for_lock,
    net_odds_after_commission,
    volume_drop_exceeded,
)
from hibs_racing.trading.broker_outbound import OutboundBrokerBlocked, negotiate_secondary_venue
from hibs_racing.features.store import connect, init_db
from hibs_racing.trading.store import ensure_trading_schema, record_simulated_trade


@pytest.fixture
def trading_db(tmp_path, monkeypatch):
    db = tmp_path / "feature_store.sqlite"
    monkeypatch.setenv("HIBS_RACING_DB_PATH", str(db))
    init_db(db)
    return db


def test_net_odds_after_commission():
    net = net_odds_after_commission(5.0, 200.0)
    assert net == pytest.approx(4.9, rel=1e-3)


def test_hedge_delta_bps_on_steam():
    assert hedge_delta_bps(8.0, 4.0) == pytest.approx(10000.0, rel=1e-2)
    assert hedge_delta_bps(8.0, 9.0) is None


def test_outbound_blocked_when_router_inactive(monkeypatch):
    monkeypatch.setenv("HIBS_LIQUIDITY_ROUTER_ACTIVE", "false")
    with pytest.raises(OutboundBrokerBlocked):
        negotiate_secondary_venue(channel="matchbook", payload={})


def test_router_records_simulated_route(trading_db, monkeypatch):
    monkeypatch.setenv("HIBS_LIQUIDITY_ROUTER_ACTIVE", "false")
    cache = MarketDeltaCache()
    router = LiquidityRouter(cache=cache, database=trading_db)
    with connect(trading_db) as conn:
        trade_id = record_simulated_trade(
            conn,
            payload_hash="abc",
            runner_id="200",
            market_id="100",
            odds=5.0,
            stake=10.0,
            status="SIMULATED",
        )
        conn.commit()
    report = router.process_tick()
    assert report["routed"] == 1
    with connect(trading_db) as conn:
        row = conn.execute(
            "SELECT chosen_channel, status FROM routing_decisions WHERE trade_id = ?",
            (trade_id,),
        ).fetchone()
    assert row is not None
    assert row["status"] == "SIMULATED_ROUTE"


def test_router_simulated_hedge_on_line_crash(trading_db, monkeypatch):
    monkeypatch.setenv("HIBS_MIN_HEDGE_DELTA_BPS", "100")
    monkeypatch.setenv("HIBS_LIQUIDITY_ROUTER_ACTIVE", "false")
    cache = MarketDeltaCache()
    cache.apply_delta(
        {"market_id": "100", "runner_id": "200", "back_odds": 4.0, "ts_ms": 1_700_000_000_000}
    )
    router = LiquidityRouter(cache=cache, database=trading_db)
    with connect(trading_db) as conn:
        trade_id = record_simulated_trade(
            conn,
            payload_hash="def",
            runner_id="200",
            market_id="100",
            odds=8.0,
            stake=10.0,
            status="SIMULATED",
        )
        conn.commit()
    report = router.process_tick()
    assert report["hedged"] == 1
    lay = lay_stake_for_lock(10.0, 8.0, 4.0)
    assert lay == pytest.approx(20.0)
    with connect(trading_db) as conn:
        row = conn.execute(
            "SELECT status, hedge_delta_bps FROM hedged_ledger_events WHERE source_trade_id = ?",
            (trade_id,),
        ).fetchone()
    assert row["status"] == "SIMULATED_HEDGE"
    assert float(row["hedge_delta_bps"]) >= 100


def test_recent_routing_decisions_helper(trading_db, monkeypatch):
    from hibs_racing.trading.liquidity_router import recent_routing_decisions

    monkeypatch.setenv("HIBS_LIQUIDITY_ROUTER_ACTIVE", "false")
    cache = MarketDeltaCache()
    router = LiquidityRouter(cache=cache, database=trading_db)
    with connect(trading_db) as conn:
        record_simulated_trade(
            conn,
            payload_hash="route-helper",
            runner_id="200",
            market_id="100",
            odds=5.0,
            stake=10.0,
            status="SIMULATED",
        )
        conn.commit()
    router.process_tick()
    rows = recent_routing_decisions(database=trading_db, limit=5)
    assert len(rows) == 1
    assert rows[0]["chosen_channel"]


def test_flight_latency_abort_threshold():
    assert adverse_selection_abort(flight_ms=451.0, pre_volume=100.0, post_volume=100.0) is True
    assert adverse_selection_abort(flight_ms=200.0, pre_volume=100.0, post_volume=100.0) is False


def test_volume_drop_abort_threshold():
    assert volume_drop_exceeded(100.0, 50.0, threshold=0.40) is True
    assert volume_drop_exceeded(100.0, 70.0, threshold=0.40) is False


def test_router_disarms_on_latency(trading_db, monkeypatch):
    monkeypatch.setenv("HIBS_LIQUIDITY_ROUTER_ACTIVE", "true")
    monkeypatch.setenv("HIBS_FLIGHT_LATENCY_MAX_MS", "10")

    def slow_negotiate(**kwargs):
        time.sleep(0.02)
        raise OutboundBrokerBlocked("simulated")

    monkeypatch.setattr(
        "hibs_racing.trading.liquidity_router.negotiate_secondary_venue",
        slow_negotiate,
    )
    cache = MarketDeltaCache()
    router = LiquidityRouter(cache=cache, database=trading_db)
    with connect(trading_db) as conn:
        trade_id = record_simulated_trade(
            conn,
            payload_hash="latency-abort",
            runner_id="200",
            market_id="100",
            odds=5.0,
            stake=10.0,
            status="SIMULATED",
            payload={"matchbook_back_volume": 500.0},
        )
        conn.commit()
    router.process_tick()
    with connect(trading_db) as conn:
        row = conn.execute(
            "SELECT status, routed_stake, flight_latency_ms FROM routing_decisions WHERE trade_id = ?",
            (trade_id,),
        ).fetchone()
    assert row is not None
    assert row["status"] == DISARMED_BY_ADVERSE_SELECTION
    assert float(row["routed_stake"]) == pytest.approx(0.0)
    assert float(row["flight_latency_ms"]) > 10


def test_router_disarms_on_volume_drop(trading_db, monkeypatch):
    monkeypatch.setenv("HIBS_LIQUIDITY_ROUTER_ACTIVE", "true")
    monkeypatch.setenv("HIBS_FLIGHT_LATENCY_MAX_MS", "5000")
    cache = MarketDeltaCache()

    def dropping_negotiate(**kwargs):
        cache.apply_delta(
            {
                "market_id": "100",
                "runner_id": "201",
                "back_odds": 5.0,
                "matchbook_back_volume": 50.0,
                "ts_ms": 2,
            }
        )
        raise OutboundBrokerBlocked("simulated")

    monkeypatch.setattr(
        "hibs_racing.trading.liquidity_router.negotiate_secondary_venue",
        dropping_negotiate,
    )
    router = LiquidityRouter(cache=cache, database=trading_db)
    with connect(trading_db) as conn:
        trade_id = record_simulated_trade(
            conn,
            payload_hash="volume-drop",
            runner_id="201",
            market_id="100",
            odds=5.0,
            stake=8.0,
            status="SIMULATED",
            payload={"matchbook_back_volume": 100.0},
        )
        conn.commit()
    router.process_tick()
    with connect(trading_db) as conn:
        row = conn.execute(
            "SELECT status, routed_stake FROM routing_decisions WHERE trade_id = ?",
            (trade_id,),
        ).fetchone()
    assert row["status"] == DISARMED_BY_ADVERSE_SELECTION
    assert float(row["routed_stake"]) == pytest.approx(0.0)
