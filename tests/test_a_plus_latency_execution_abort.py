"""A+ ops: latency breaches drop in-play execution paths."""

from __future__ import annotations

import asyncio
import json
import time

import pytest

from hibs_racing.trading.config import liquidity_router_active
from hibs_racing.trading.delta_cache import MarketDeltaCache
from hibs_racing.trading.liquidity_router import (
    DISARMED_BY_ADVERSE_SELECTION,
    LiquidityRouter,
    adverse_selection_abort,
)
from hibs_racing.trading.runner_disarm_registry import is_disarmed
from hibs_racing.features.store import connect, init_db
from hibs_racing.trading.store import ensure_trading_schema, record_simulated_trade


@pytest.fixture
def trading_db(tmp_path, monkeypatch):
    db = tmp_path / "feature_store.sqlite"
    monkeypatch.setenv("HIBS_RACING_DB_PATH", str(db))
    init_db(db)
    return db


def test_adverse_selection_abort_blocks_execution():
    assert adverse_selection_abort(flight_ms=500.0, pre_volume=100.0, post_volume=100.0) is True
    assert adverse_selection_abort(flight_ms=50.0, pre_volume=100.0, post_volume=100.0) is False


@pytest.mark.asyncio
async def test_inplay_loop_drops_on_latency_breach(trading_db, monkeypatch, tmp_path):
    monkeypatch.setenv("HIBS_LIQUIDITY_ROUTER_ACTIVE", "true")
    monkeypatch.setenv("HIBS_FLIGHT_LATENCY_MAX_MS", "100")
    monkeypatch.setenv("HIBS_RUNNER_DISARM_FILE", str(tmp_path / "disarm.json"))
    cache = MarketDeltaCache()
    router = LiquidityRouter(cache=cache, database=trading_db)
    with connect(trading_db) as conn:
        trade_id = record_simulated_trade(
            conn,
            payload_hash="lat1",
            runner_id="runner-99",
            market_id="m1",
            odds=5.0,
            stake=10.0,
            status="SIMULATED",
            payload={"matchbook_back_volume": 100.0},
        )
        conn.commit()
    row = {
        "trade_id": trade_id,
        "runner_id": "runner-99",
        "market_id": "m1",
        "odds": 5.0,
        "stake": 10.0,
        "payload_json": json.dumps({"matchbook_back_volume": 100.0}),
    }
    request = router.build_venue_request(row, channel="matchbook", odds=5.0)

    def slow_submit(_request):
        time.sleep(0.15)
        return {"ok": True, "authoritative": True}

    router._venue_submit = slow_submit  # type: ignore[method-assign]
    router._inplay_queue.append(
        {
            "channel": "matchbook",
            "request": request,
            "row": row,
            "quotes": router.score_venues(5.0),
            "pre_volume": 100.0,
        }
    )
    report = await router.process_inplay_execution_loop()
    assert report["processed"] == 1
    with connect(trading_db) as conn:
        decision = conn.execute(
            "SELECT status FROM routing_decisions WHERE trade_id = ? ORDER BY created_at DESC LIMIT 1",
            (trade_id,),
        ).fetchone()
    assert decision is not None
    assert decision["status"] == DISARMED_BY_ADVERSE_SELECTION
    assert is_disarmed("runner-99")


def test_router_dedup_survives_reinstantiation(trading_db, monkeypatch):
    monkeypatch.setenv("HIBS_LIQUIDITY_ROUTER_ACTIVE", "false")
    cache = MarketDeltaCache()
    router_a = LiquidityRouter(cache=cache, database=trading_db)
    with connect(trading_db) as conn:
        trade_id = record_simulated_trade(
            conn,
            payload_hash="dedup1",
            runner_id="200",
            market_id="100",
            odds=5.0,
            stake=10.0,
            status="SIMULATED",
        )
        conn.commit()
    assert router_a.process_tick()["routed"] == 1
    router_b = LiquidityRouter(cache=cache, database=trading_db)
    assert router_b.process_tick()["routed"] == 0
