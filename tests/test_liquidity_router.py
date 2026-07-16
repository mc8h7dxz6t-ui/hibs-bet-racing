"""Tests for liquidity router (simulation only)."""

from __future__ import annotations

import pytest

from hibs_racing.trading.config import liquidity_router_active
from hibs_racing.trading.delta_cache import MarketDeltaCache
from hibs_racing.trading.liquidity_router import (
    LiquidityRouter,
    hedge_delta_bps,
    lay_stake_for_lock,
    net_odds_after_commission,
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
