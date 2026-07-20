"""Atomic pre-commit execution governor — CAS wallet, idempotency, slippage/latency gates."""

from __future__ import annotations

import hashlib
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
from hibs_racing.trading.config import (
    execution_latency_max_ms,
    idempotency_window_ms,
    live_trading_enabled,
    slippage_max_ticks,
    stream_tick_size,
)
from hibs_racing.trading.delta_cache import MarketDeltaCache
from hibs_racing.trading.exchange_gateway import LiveExchangeWriteDisabled, dispatch_live_order
from hibs_racing.trading.store import (
    cas_reserve_capital,
    ensure_trading_schema,
    get_wallet_state,
    record_idempotency_hit,
    record_simulated_trade,
    release_reserved_capital,
)

logger = logging.getLogger(__name__)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def payload_signature(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def odds_slippage_ticks(requested: float, market: float, *, tick_size: float) -> float:
    if tick_size <= 0:
        return 0.0
    return abs(requested - market) / tick_size


@dataclass(frozen=True)
class GovernorVerdict:
    allowed: bool
    status: str
    reason: str
    payload_hash: str
    packet_delay_ms: float | None = None
    slippage_ticks: float | None = None
    trade_id: str | None = None
    wallet_version: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "status": self.status,
            "reason": self.reason,
            "payload_hash": self.payload_hash,
            "packet_delay_ms": self.packet_delay_ms,
            "slippage_ticks": self.slippage_ticks,
            "trade_id": self.trade_id,
            "wallet_version": self.wallet_version,
            "live_trading_enabled": live_trading_enabled(),
        }


@dataclass
class IdempotencyGuard:
    """In-memory + SQLite duplicate rejection within configurable window."""

    window_ms: int = field(default_factory=idempotency_window_ms)
    _recent: dict[str, float] = field(default_factory=dict)

    def is_duplicate(self, payload_hash: str, *, now_ms: float | None = None) -> bool:
        now = now_ms if now_ms is not None else time.time() * 1000
        cutoff = now - self.window_ms
        stale = [k for k, ts in self._recent.items() if ts < cutoff]
        for k in stale:
            del self._recent[k]
        last = self._recent.get(payload_hash)
        if last is not None and last >= cutoff:
            return True
        self._recent[payload_hash] = now
        return False


@dataclass
class ExecutionGovernor:
    """
    Strict transactional validation controller before any order dispatch.

    - CAS wallet reserve against feature_store.sqlite trading_wallet_state
    - Idempotency hash guard (default 5000ms)
    - Latency + slippage gates from stream cache
    """

    cache: MarketDeltaCache
    database: Path | None = None
    wallet_id: str = "default"
    idempotency: IdempotencyGuard = field(default_factory=IdempotencyGuard)

    def _db(self) -> Path:
        return ensure_trading_schema(self.database or db_path(load_config()))

    def _record_intent(self, payload: dict[str, Any], verdict: GovernorVerdict) -> None:
        try:
            from hibs_racing.trading.execution_intent_ledger import append_execution_intent

            append_execution_intent(
                verdict=verdict.to_dict(),
                source="execution_governor",
                trace_id=str(payload.get("trace_id") or payload.get("client_order_id") or ""),
            )
        except Exception:
            pass

    def pre_commit(self, payload: dict[str, Any], *, received_at_ms: float | None = None) -> GovernorVerdict:
        sig = payload_signature(payload)
        now_ms = received_at_ms if received_at_ms is not None else time.time() * 1000
        created_ms = float(payload.get("created_at_ms") or now_ms)
        packet_delay_ms = max(0.0, now_ms - created_ms)

        if self.idempotency.is_duplicate(sig, now_ms=now_ms):
            return GovernorVerdict(
                allowed=False,
                status="IDEMPOTENCY_REJECT",
                reason=f"duplicate payload within {self.idempotency.window_ms}ms",
                payload_hash=sig,
                packet_delay_ms=packet_delay_ms,
            )

        max_latency = execution_latency_max_ms()
        if packet_delay_ms > max_latency:
            return GovernorVerdict(
                allowed=False,
                status="LATENCY_REJECT",
                reason=f"packet delay {packet_delay_ms:.1f}ms > {max_latency}ms",
                payload_hash=sig,
                packet_delay_ms=packet_delay_ms,
            )

        market_id = str(payload.get("market_id") or "")
        runner_id = str(payload.get("runner_id") or "")
        requested_odds = float(payload.get("odds") or 0)
        tick = self.cache.get(market_id, runner_id) if market_id and runner_id else None
        slip_ticks: float | None = None
        if tick and tick.back_odds and requested_odds > 0:
            slip_ticks = odds_slippage_ticks(requested_odds, tick.back_odds, tick_size=stream_tick_size())
            if slip_ticks > slippage_max_ticks():
                return GovernorVerdict(
                    allowed=False,
                    status="SLIPPAGE_REJECT",
                    reason=(
                        f"slippage {slip_ticks:.2f} ticks > {slippage_max_ticks()} "
                        f"(requested={requested_odds}, market={tick.back_odds})"
                    ),
                    payload_hash=sig,
                    packet_delay_ms=packet_delay_ms,
                    slippage_ticks=slip_ticks,
                )

        stake = float(payload.get("stake") or 0)
        if stake <= 0:
            return GovernorVerdict(
                allowed=False,
                status="VALIDATION_REJECT",
                reason="stake must be positive",
                payload_hash=sig,
                packet_delay_ms=packet_delay_ms,
                slippage_ticks=slip_ticks,
            )

        db = self._db()
        with connect(db) as conn:
            if record_idempotency_hit(conn, sig, now=_utc_now()):
                conn.commit()
                return GovernorVerdict(
                    allowed=False,
                    status="IDEMPOTENCY_REJECT",
                    reason="duplicate payload in persistent guard",
                    payload_hash=sig,
                    packet_delay_ms=packet_delay_ms,
                    slippage_ticks=slip_ticks,
                )

            wallet = get_wallet_state(conn, wallet_id=self.wallet_id)
            version = int(wallet.get("version") or 0)
            ok, reason, new_version = cas_reserve_capital(
                conn,
                wallet_id=self.wallet_id,
                expected_version=version,
                stake=stake,
            )
            if not ok:
                conn.commit()
                return GovernorVerdict(
                    allowed=False,
                    status="CAPITAL_REJECT",
                    reason=reason,
                    payload_hash=sig,
                    packet_delay_ms=packet_delay_ms,
                    slippage_ticks=slip_ticks,
                    wallet_version=version,
                )
            conn.commit()

        return GovernorVerdict(
            allowed=True,
            status="PRE_COMMIT_OK",
            reason="gates passed",
            payload_hash=sig,
            packet_delay_ms=packet_delay_ms,
            slippage_ticks=slip_ticks,
            wallet_version=new_version,
        )

    def dispatch(self, payload: dict[str, Any], *, received_at_ms: float | None = None) -> GovernorVerdict:
        verdict = self._dispatch_impl(payload, received_at_ms=received_at_ms)
        self._record_intent(payload, verdict)
        return verdict

    def _dispatch_impl(self, payload: dict[str, Any], *, received_at_ms: float | None = None) -> GovernorVerdict:
        verdict = self.pre_commit(payload, received_at_ms=received_at_ms)
        stake = float(payload.get("stake") or 0)
        db = self._db()

        if not verdict.allowed:
            with connect(db) as conn:
                trade_id = record_simulated_trade(
                    conn,
                    payload_hash=verdict.payload_hash,
                    runner_id=str(payload.get("runner_id") or "") or None,
                    market_id=str(payload.get("market_id") or "") or None,
                    odds=float(payload.get("odds")) if payload.get("odds") is not None else None,
                    stake=stake or None,
                    status=verdict.status,
                    reject_reason=verdict.reason,
                    packet_delay_ms=verdict.packet_delay_ms,
                    slippage_ticks=verdict.slippage_ticks,
                    payload=payload,
                )
                conn.commit()
            return GovernorVerdict(
                allowed=False,
                status=verdict.status,
                reason=verdict.reason,
                payload_hash=verdict.payload_hash,
                packet_delay_ms=verdict.packet_delay_ms,
                slippage_ticks=verdict.slippage_ticks,
                trade_id=trade_id,
                wallet_version=verdict.wallet_version,
            )

        if not live_trading_enabled():
            with connect(db) as conn:
                trade_id = record_simulated_trade(
                    conn,
                    payload_hash=verdict.payload_hash,
                    runner_id=str(payload.get("runner_id") or "") or None,
                    market_id=str(payload.get("market_id") or "") or None,
                    odds=float(payload.get("odds")) if payload.get("odds") is not None else None,
                    stake=stake,
                    status="SIMULATED",
                    reject_reason=None,
                    packet_delay_ms=verdict.packet_delay_ms,
                    slippage_ticks=verdict.slippage_ticks,
                    payload=payload,
                )
                release_reserved_capital(conn, wallet_id=self.wallet_id, stake=stake)
                conn.commit()
            logger.info("simulated order recorded trade_id=%s hash=%s", trade_id, verdict.payload_hash[:12])
            return GovernorVerdict(
                allowed=True,
                status="SIMULATED",
                reason="HIBS_LIVE_TRADING_ENABLED=false",
                payload_hash=verdict.payload_hash,
                packet_delay_ms=verdict.packet_delay_ms,
                slippage_ticks=verdict.slippage_ticks,
                trade_id=trade_id,
                wallet_version=verdict.wallet_version,
            )

        try:
            external = dispatch_live_order(payload)
        except LiveExchangeWriteDisabled as exc:
            with connect(db) as conn:
                trade_id = record_simulated_trade(
                    conn,
                    payload_hash=verdict.payload_hash,
                    runner_id=str(payload.get("runner_id") or "") or None,
                    market_id=str(payload.get("market_id") or "") or None,
                    odds=float(payload.get("odds")) if payload.get("odds") is not None else None,
                    stake=stake,
                    status="LIVE_STUBBED",
                    reject_reason=str(exc),
                    packet_delay_ms=verdict.packet_delay_ms,
                    slippage_ticks=verdict.slippage_ticks,
                    payload=payload,
                )
                release_reserved_capital(conn, wallet_id=self.wallet_id, stake=stake)
                conn.commit()
            return GovernorVerdict(
                allowed=False,
                status="LIVE_STUBBED",
                reason=str(exc),
                payload_hash=verdict.payload_hash,
                packet_delay_ms=verdict.packet_delay_ms,
                slippage_ticks=verdict.slippage_ticks,
                trade_id=trade_id,
                wallet_version=verdict.wallet_version,
            )
        except Exception as exc:
            with connect(db) as conn:
                release_reserved_capital(conn, wallet_id=self.wallet_id, stake=stake)
                trade_id = record_simulated_trade(
                    conn,
                    payload_hash=verdict.payload_hash,
                    runner_id=str(payload.get("runner_id") or "") or None,
                    market_id=str(payload.get("market_id") or "") or None,
                    odds=float(payload.get("odds")) if payload.get("odds") is not None else None,
                    stake=stake,
                    status="LIVE_ERROR",
                    reject_reason=str(exc),
                    packet_delay_ms=verdict.packet_delay_ms,
                    slippage_ticks=verdict.slippage_ticks,
                    payload=payload,
                )
                conn.commit()
            logger.exception("live dispatch failed")
            return GovernorVerdict(
                allowed=False,
                status="LIVE_ERROR",
                reason=str(exc),
                payload_hash=verdict.payload_hash,
                packet_delay_ms=verdict.packet_delay_ms,
                slippage_ticks=verdict.slippage_ticks,
                trade_id=trade_id,
                wallet_version=verdict.wallet_version,
            )

        _ = external
        with connect(db) as conn:
            trade_id = record_simulated_trade(
                conn,
                payload_hash=verdict.payload_hash,
                runner_id=str(payload.get("runner_id") or "") or None,
                market_id=str(payload.get("market_id") or "") or None,
                odds=float(payload.get("odds")) if payload.get("odds") is not None else None,
                stake=stake,
                status="LIVE_ROUTED",
                reject_reason=None,
                packet_delay_ms=verdict.packet_delay_ms,
                slippage_ticks=verdict.slippage_ticks,
                payload={**payload, "external_ack": external},
            )
            conn.commit()
        return GovernorVerdict(
            allowed=True,
            status="LIVE_ROUTED",
            reason="live exchange ack",
            payload_hash=verdict.payload_hash,
            packet_delay_ms=verdict.packet_delay_ms,
            slippage_ticks=verdict.slippage_ticks,
            trade_id=trade_id,
            wallet_version=verdict.wallet_version,
        )


def build_order_payload(
    *,
    market_id: str,
    runner_id: str,
    odds: float,
    stake: float,
    side: str = "back",
    client_order_id: str | None = None,
) -> dict[str, Any]:
    return {
        "client_order_id": client_order_id or str(uuid.uuid4()),
        "market_id": market_id,
        "runner_id": runner_id,
        "odds": odds,
        "stake": stake,
        "side": side,
        "created_at_ms": int(time.time() * 1000),
    }
