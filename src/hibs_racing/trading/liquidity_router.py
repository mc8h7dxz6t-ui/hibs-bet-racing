"""Liquidity cross-match router — venue scoring + simulated delta-hedge ledger."""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hibs_racing.config import db_path, load_config
from hibs_racing.features.store import connect
from hibs_racing.trading.broker_outbound import OutboundBrokerBlocked, negotiate_secondary_venue
from hibs_racing.trading.config import (
    adverse_selection_volume_drop_pct,
    allowed_routing_channels,
    flight_latency_max_ms,
    liquidity_router_active,
    max_venue_commission_bps,
    min_hedge_delta_bps,
)
from hibs_racing.trading.delta_cache import MarketDeltaCache
from hibs_racing.trading.order_ttl import (
    INPLAY_ORDER_TIMED_OUT_ABORT,
    INPLAY_ORDER_TTL_MS,
    InPlayOrderTracker,
    default_cancel_fn,
    log_timed_out_abort_to_ledger,
)
from hibs_racing.trading.runner_disarm_registry import disarm_runner, is_disarmed
from hibs_racing.trading.store import ensure_trading_schema

logger = logging.getLogger(__name__)

from hibs_racing.utils.monetization import VENUE_COMMISSION_BPS, commission_by_channel

DEFAULT_COMMISSION_BPS: dict[str, float] = dict(VENUE_COMMISSION_BPS)

DISARMED_BY_ADVERSE_SELECTION = "DISARMED_BY_ADVERSE_SELECTION"


def _parse_payload_json(row: dict[str, Any]) -> dict[str, Any]:
    raw = row.get("payload_json")
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _matchbook_back_volume(row: dict[str, Any], cache: MarketDeltaCache, *, prefer_cache: bool = False) -> float | None:
    market_id = str(row.get("market_id") or "")
    runner_id = str(row.get("runner_id") or "")
    if prefer_cache and market_id and runner_id:
        tick = cache.get(market_id, runner_id)
        if tick and tick.back_volume is not None:
            return float(tick.back_volume)
    payload = _parse_payload_json(row)
    raw = payload.get("matchbook_back_volume")
    if raw is None:
        raw = payload.get("back_volume")
    if raw is not None:
        try:
            return float(raw)
        except (TypeError, ValueError):
            pass
    if market_id and runner_id:
        tick = cache.get(market_id, runner_id)
        if tick and tick.back_volume is not None:
            return float(tick.back_volume)
    return None


def flight_latency_ms(start_ns: int, end_ns: int) -> float:
    return (end_ns - start_ns) / 1_000_000.0


def volume_drop_exceeded(pre: float | None, post: float | None, *, threshold: float | None = None) -> bool:
    if pre is None or post is None or pre <= 0:
        return False
    drop = threshold if threshold is not None else adverse_selection_volume_drop_pct()
    return post <= pre * (1.0 - drop)


def adverse_selection_abort(
    *,
    flight_ms: float,
    pre_volume: float | None,
    post_volume: float | None,
    max_latency_ms: int | None = None,
) -> bool:
    cap = max_latency_ms if max_latency_ms is not None else flight_latency_max_ms()
    if flight_ms > cap:
        return True
    return volume_drop_exceeded(pre_volume, post_volume)


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
    commission_by_channel: dict[str, float] = field(default_factory=commission_by_channel)
    order_tracker: InPlayOrderTracker = field(default_factory=InPlayOrderTracker)
    _inplay_queue: list[dict[str, Any]] = field(default_factory=list)
    _ttl_aborts: int = 0

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
        drift_blocked = 0
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
                rec = dict(row)
                trade_id = str(rec["trade_id"])
                runner_id = str(rec.get("runner_id") or "")
                if runner_id and is_disarmed(runner_id):
                    drift_blocked += 1
                    continue
                if runner_id:
                    try:
                        from hibs_predictor.drift_gate import validate_market_velocity

                        drift = validate_market_velocity(runner_id, database=db)
                        if not drift.get("ok", True):
                            drift_blocked += 1
                            continue
                    except ImportError:
                        pass
                    except Exception as exc:
                        logger.debug("drift_gate skipped trade=%s: %s", trade_id[:8], exc)
                if not self._trade_already_routed(conn, trade_id):
                    if self._route_trade(conn, rec):
                        routed += 1
                if trade_id not in self._hedged_trade_ids(conn):
                    if self._maybe_hedge(conn, rec):
                        hedged += 1
            conn.commit()
        return {
            "liquidity_router_active": liquidity_router_active(),
            "routed": routed,
            "hedged": hedged,
            "drift_blocked": drift_blocked,
            "inplay_queue_depth": len(self._inplay_queue),
            "ttl_aborts": self._ttl_aborts,
            "order_ttl_ms": INPLAY_ORDER_TTL_MS,
        }

    def _hedged_trade_ids(self, conn) -> set[str]:
        rows = conn.execute("SELECT source_trade_id FROM hedged_ledger_events").fetchall()
        return {str(r["source_trade_id"]) for r in rows}

    def _trade_already_routed(self, conn, trade_id: str) -> bool:
        row = conn.execute(
            "SELECT 1 FROM routing_decisions WHERE trade_id = ? LIMIT 1",
            (trade_id,),
        ).fetchone()
        return row is not None

    def build_venue_request(self, row: dict[str, Any], *, channel: str, odds: float) -> dict[str, Any]:
        pre_volume = _matchbook_back_volume(row, self.cache, prefer_cache=False)
        base = {
            "trade_id": row["trade_id"],
            "runner_id": row.get("runner_id"),
            "market_id": row.get("market_id"),
            "odds": odds,
            "stake": row.get("stake"),
            "channel": channel,
            "created_at_ms": int(time.time() * 1000),
            "matchbook_back_volume": pre_volume,
        }
        return self.order_tracker.attach_expiry(base)

    def _venue_submit(self, request: dict[str, Any]) -> dict[str, Any]:
        channel = str(request.get("channel") or "")
        stake = float(request.get("stake") or 0)
        payload = dict(request)
        payload["stake"] = stake
        negotiate_secondary_venue(channel=channel, payload=payload)
        return {"ok": True, "authoritative": True, "channel": channel, "routed_stake": stake}

    async def process_inplay_execution_loop(self) -> dict[str, Any]:
        """Drain queued live routes under strict TTL + adverse-selection flight guard."""
        if not self._inplay_queue:
            return {"processed": 0, "ttl_aborts": self._ttl_aborts}
        processed = 0
        queue = list(self._inplay_queue)
        self._inplay_queue.clear()
        for item in queue:
            channel = str(item["channel"])
            request = dict(item["request"])
            row = item["row"]
            quotes = item.get("quotes") or []
            pre_volume = item.get("pre_volume")
            if pre_volume is None:
                pre_volume = _matchbook_back_volume(row, self.cache, prefer_cache=False)
            if self.order_tracker.is_muted(channel):
                self._record_route_decision(
                    row,
                    channel=channel,
                    quotes=quotes,
                    status=INPLAY_ORDER_TIMED_OUT_ABORT,
                    outbound_blocked=1,
                    routed_stake=0.0,
                )
                continue
            flight_start_ns = time.perf_counter_ns()
            try:
                result = await self.order_tracker.submit_with_ttl(
                    channel=channel,
                    request=request,
                    submit_fn=self._venue_submit,
                    cancel_fn=default_cancel_fn,
                    confirm_fn=lambda ack: bool(ack.get("authoritative")),
                    log_abort=log_timed_out_abort_to_ledger,
                )
            except Exception as exc:
                logger.warning("inplay execution loop error: %s", exc)
                continue
            flight_end_ns = time.perf_counter_ns()
            flight_ms = flight_latency_ms(flight_start_ns, flight_end_ns)
            post_volume = _matchbook_back_volume(row, self.cache, prefer_cache=True)
            routed_stake = float(row.get("stake") or 0)
            status = "LIVE_ROUTED"
            outbound_blocked = 0
            if result.get("status") == INPLAY_ORDER_TIMED_OUT_ABORT:
                self._ttl_aborts += 1
                status = INPLAY_ORDER_TIMED_OUT_ABORT
                outbound_blocked = 1
                routed_stake = 0.0
            elif adverse_selection_abort(
                flight_ms=flight_ms, pre_volume=pre_volume, post_volume=post_volume
            ):
                status = DISARMED_BY_ADVERSE_SELECTION
                outbound_blocked = 1
                routed_stake = 0.0
                runner_id = str(row.get("runner_id") or "")
                if runner_id:
                    disarm_runner(runner_id, reason="adverse_selection")
                logger.warning(
                    "adverse selection abort trade=%s flight_ms=%.1f pre_vol=%s post_vol=%s",
                    str(row["trade_id"])[:8],
                    flight_ms,
                    pre_volume,
                    post_volume,
                )
            processed += 1
            self._record_route_decision(
                row,
                channel=channel,
                quotes=quotes,
                status=status,
                outbound_blocked=outbound_blocked,
                flight_latency_ms=flight_ms,
                routed_stake=routed_stake,
                matchbook_back_volume_pre=pre_volume,
                matchbook_back_volume_post=post_volume,
            )
        return {"processed": processed, "ttl_aborts": self._ttl_aborts}

    def _record_route_decision(
        self,
        row: dict[str, Any],
        *,
        channel: str,
        quotes: list[VenueQuote],
        status: str,
        outbound_blocked: int,
        flight_latency_ms: float | None = None,
        routed_stake: float | None = None,
        matchbook_back_volume_pre: float | None = None,
        matchbook_back_volume_post: float | None = None,
    ) -> None:
        best = quotes[0] if quotes else VenueQuote(channel=channel, gross_odds=0.0, commission_bps=0.0, net_odds=0.0)
        db = self._db()
        stake = routed_stake if routed_stake is not None else float(row.get("stake") or 0)
        with connect(db) as conn:
            conn.execute(
                """
                INSERT INTO routing_decisions (
                    decision_id, trade_id, runner_id, market_id, chosen_channel,
                    gross_odds, net_odds, commission_bps, status, outbound_blocked,
                    flight_latency_ms, routed_stake, matchbook_back_volume_pre,
                    matchbook_back_volume_post, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    row["trade_id"],
                    row.get("runner_id"),
                    row.get("market_id"),
                    channel,
                    best.gross_odds,
                    best.net_odds,
                    best.commission_bps,
                    status,
                    outbound_blocked,
                    round(flight_latency_ms, 3) if flight_latency_ms is not None else None,
                    stake,
                    matchbook_back_volume_pre,
                    matchbook_back_volume_post,
                    _utc_now(),
                ),
            )
            conn.commit()

    def _route_trade(self, conn, row: dict[str, Any]) -> bool:
        runner_id = str(row.get("runner_id") or "")
        if runner_id and is_disarmed(runner_id):
            return False
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
            request = self.build_venue_request(row, channel=best.channel, odds=odds)
            pre_volume = _matchbook_back_volume(row, self.cache, prefer_cache=False)
            self._inplay_queue.append(
                {
                    "channel": best.channel,
                    "request": request,
                    "row": row,
                    "quotes": quotes,
                    "pre_volume": pre_volume,
                }
            )
            return True
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
        runner_id = str(row.get("runner_id") or "")
        if runner_id and is_disarmed(runner_id):
            return False
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
