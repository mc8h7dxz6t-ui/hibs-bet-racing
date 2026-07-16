"""Liquidity cross-match router — venue scoring + simulated delta-hedge ledger."""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hibs_racing.config import db_path, load_config
from hibs_racing.features.store import connect
from hibs_racing.trading.broker_outbound import OutboundBrokerBlocked, negotiate_secondary_venue
from hibs_racing.trading.config import (
    allowed_routing_channels,
    liquidity_router_active,
    max_venue_commission_bps,
    min_hedge_delta_bps,
)
from hibs_racing.trading.delta_cache import MarketDeltaCache
from hibs_racing.trading.store import ensure_trading_schema

logger = logging.getLogger(__name__)

DEFAULT_COMMISSION_BPS: dict[str, float] = {
    "matchbook": 200.0,
    "betfair_stub": 250.0,
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def net_odds_after_commission(gross_odds: float, commission_bps: float) -> float:
    if gross_odds <= 1.0:
        return gross_odds
    fee = min(max(commission_bps, 0.0), max_venue_commission_bps()) / 10000.0
    return gross_odds * (1.0 - fee)


def hedge_delta_bps(back_odds: float, current_odds: float) -> float | None:
    if back_odds <= 1.0 or current_odds <= 1.0:
        return None
    if current_odds >= back_odds:
        return None
    return ((back_odds / current_odds) - 1.0) * 10000.0


def lay_stake_for_lock(back_stake: float, back_odds: float, lay_odds: float) -> float:
    if lay_odds <= 1.0 or back_stake <= 0:
        return 0.0
    return back_stake * back_odds / lay_odds


def locked_margin_units(back_stake: float, back_odds: float, lay_stake: float, lay_odds: float) -> float:
    """Approximate locked margin when line steams in (back high, lay lower)."""
    win_pnl = back_stake * (back_odds - 1.0) - lay_stake * (lay_odds - 1.0)
    lose_pnl = -back_stake + lay_stake
    return min(win_pnl, lose_pnl)


@dataclass
class VenueQuote:
    channel: str
    gross_odds: float
    commission_bps: float
    net_odds: float


@dataclass
class LiquidityRouter:
    cache: MarketDeltaCache
    database: Path | None = None
    commission_by_channel: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_COMMISSION_BPS))
    _processed_trades: set[str] = field(default_factory=set)
    _hedged_trades: set[str] = field(default_factory=set)

    def _db(self) -> Path:
        return ensure_trading_schema(self.database or db_path(load_config()))

    def score_venues(self, gross_odds: float) -> list[VenueQuote]:
        quotes: list[VenueQuote] = []
        cap = max_venue_commission_bps()
        for channel in allowed_routing_channels():
            bps = min(self.commission_by_channel.get(channel, cap), cap)
            if bps > cap:
                continue
            net = net_odds_after_commission(gross_odds, bps)
            quotes.append(VenueQuote(channel=channel, gross_odds=gross_odds, commission_bps=bps, net_odds=net))
        quotes.sort(key=lambda q: q.net_odds, reverse=True)
        return quotes

    def process_tick(self) -> dict[str, Any]:
        """One router cycle: route new simulated trades + evaluate hedge opportunities."""
        db = self._db()
        routed = 0
        hedged = 0
        with connect(db) as conn:
            rows = conn.execute(
                """
                SELECT trade_id, runner_id, market_id, odds, stake, status, payload_json
                FROM simulated_trades
                WHERE status IN ('SIMULATED', 'LIVE_ROUTED')
                ORDER BY created_at DESC
                LIMIT 50
                """
            ).fetchall()
            for row in rows:
                trade_id = str(row["trade_id"])
                if trade_id not in self._processed_trades:
                    if self._route_trade(conn, dict(row)):
                        routed += 1
                    self._processed_trades.add(trade_id)
                if trade_id not in self._hedged_trades:
                    if self._maybe_hedge(conn, dict(row)):
                        hedged += 1
                        self._hedged_trades.add(trade_id)
            conn.commit()
        return {
            "liquidity_router_active": liquidity_router_active(),
            "routed": routed,
            "hedged": hedged,
            "processed_trades": len(self._processed_trades),
        }

    def _route_trade(self, conn, row: dict[str, Any]) -> bool:
        odds = float(row["odds"] or 0)
        if odds <= 1.0:
            return False
        quotes = self.score_venues(odds)
        if not quotes:
            return False
        best = quotes[0]
        existing = conn.execute(
            "SELECT 1 FROM routing_decisions WHERE trade_id = ? LIMIT 1",
            (row["trade_id"],),
        ).fetchone()
        if existing:
            return False
        outbound_blocked = 1
        status = "SIMULATED_ROUTE"
        if liquidity_router_active():
            try:
                negotiate_secondary_venue(
                    channel=best.channel,
                    payload={"trade_id": row["trade_id"], "odds": odds, "stake": row["stake"]},
                )
            except OutboundBrokerBlocked:
                status = "OUTBOUND_BLOCKED"
            except Exception as exc:
                status = "ROUTE_ERROR"
                logger.warning("router outbound error: %s", exc)
        conn.execute(
            """
            INSERT INTO routing_decisions (
                decision_id, trade_id, runner_id, market_id, chosen_channel,
                gross_odds, net_odds, commission_bps, status, outbound_blocked, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                row["trade_id"],
                row.get("runner_id"),
                row.get("market_id"),
                best.channel,
                best.gross_odds,
                best.net_odds,
                best.commission_bps,
                status,
                outbound_blocked,
                _utc_now(),
            ),
        )
        return True

    def _maybe_hedge(self, conn, row: dict[str, Any]) -> bool:
        back_odds = float(row["odds"] or 0)
        back_stake = float(row["stake"] or 0)
        market_id = str(row.get("market_id") or "")
        runner_id = str(row.get("runner_id") or "")
        if back_odds <= 1.0 or back_stake <= 0 or not market_id or not runner_id:
            return False
        tick = self.cache.get(market_id, runner_id)
        current = tick.back_odds if tick and tick.back_odds else None
        if current is None:
            return False
        delta = hedge_delta_bps(back_odds, current)
        if delta is None or delta < min_hedge_delta_bps():
            return False
        existing = conn.execute(
            "SELECT 1 FROM hedged_ledger_events WHERE source_trade_id = ? LIMIT 1",
            (row["trade_id"],),
        ).fetchone()
        if existing:
            return False
        lay_odds = current
        lay_stake = lay_stake_for_lock(back_stake, back_odds, lay_odds)
        margin = locked_margin_units(back_stake, back_odds, lay_stake, lay_odds)
        quotes = self.score_venues(lay_odds)
        channel = quotes[0].channel if quotes else "matchbook"
        conn.execute(
            """
            INSERT INTO hedged_ledger_events (
                event_id, source_trade_id, runner_id, market_id,
                back_odds, lay_odds, back_stake, lay_stake,
                hedge_delta_bps, locked_margin_units, channel, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                row["trade_id"],
                runner_id,
                market_id,
                back_odds,
                lay_odds,
                back_stake,
                lay_stake,
                delta,
                margin,
                channel,
                "SIMULATED_HEDGE",
                _utc_now(),
            ),
        )
        logger.info(
            "simulated hedge trade=%s delta_bps=%.0f margin=%.4f",
            row["trade_id"][:8],
            delta,
            margin,
        )
        return True


def recent_hedged_events(database: Path | None = None, *, limit: int = 20) -> list[dict[str, Any]]:
    db = ensure_trading_schema(database)
    with connect(db) as conn:
        rows = conn.execute(
            "SELECT * FROM hedged_ledger_events ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def recent_routing_decisions(database: Path | None = None, *, limit: int = 20) -> list[dict[str, Any]]:
    db = ensure_trading_schema(database)
    with connect(db) as conn:
        rows = conn.execute(
            "SELECT * FROM routing_decisions ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]
