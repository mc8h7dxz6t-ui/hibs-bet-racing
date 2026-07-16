"""Persistent async WebSocket stream listener — delta cache ingestion (no HTTP polling)."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from hibs_racing.trading.config import stream_ws_url
from hibs_racing.trading.delta_cache import MarketDeltaCache
from hibs_racing.trading.ws_transport import AsyncWebSocketTransport, WebSocketTransportError

logger = logging.getLogger(__name__)

DEFAULT_STREAM_PATH = "/edge/stream/v1/prices"


@dataclass
class StreamListenerStats:
    connected: bool = False
    messages_received: int = 0
    deltas_applied: int = 0
    reconnects: int = 0
    last_error: str | None = None
    last_message_at_ms: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "connected": self.connected,
            "messages_received": self.messages_received,
            "deltas_applied": self.deltas_applied,
            "reconnects": self.reconnects,
            "last_error": self.last_error,
            "last_message_at_ms": self.last_message_at_ms,
        }


@dataclass
class StreamListener:
    """
    Non-blocking WebSocket client for exchange streaming deltas.

    Uses configurable HIBS_MATCHBOOK_STREAM_WS_URL — no REST interval polling.
    When URL is unset, runs idle until inject_delta() is called (daemon/tests).
    """

    cache: MarketDeltaCache = field(default_factory=MarketDeltaCache)
    ws_url: str | None = None
    session_token: str | None = None
    reconnect_base_seconds: float = 1.0
    reconnect_max_seconds: float = 30.0
    stats: StreamListenerStats = field(default_factory=StreamListenerStats)
    _transport: AsyncWebSocketTransport | None = field(default=None, repr=False)
    _stop: asyncio.Event = field(default_factory=asyncio.Event, repr=False)
    _inject_queue: asyncio.Queue[dict[str, Any]] = field(default_factory=asyncio.Queue, repr=False)

    def resolve_ws_url(self) -> str:
        return (self.ws_url or stream_ws_url() or "").strip()

    def inject_delta(self, delta: dict[str, Any]):
        """Test/daemon hook — push a delta without WebSocket (still no HTTP polling)."""
        tick = self.cache.apply_delta(delta)
        if tick is not None:
            self.stats.deltas_applied += 1
            self.stats.last_message_at_ms = tick.updated_at_ms
        try:
            self._inject_queue.put_nowait(delta)
        except asyncio.QueueFull:
            pass
        return tick

    async def run(self) -> None:
        url = self.resolve_ws_url()
        if not url:
            logger.warning(
                "HIBS_MATCHBOOK_STREAM_WS_URL unset — stream listener idle (inject_delta only, no HTTP poll)"
            )
            await self._run_inject_only()
            return
        backoff = self.reconnect_base_seconds
        while not self._stop.is_set():
            try:
                await self._connect_and_consume(url)
                backoff = self.reconnect_base_seconds
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.stats.connected = False
                self.stats.last_error = str(exc)
                self.stats.reconnects += 1
                logger.warning("stream listener reconnect after error: %s", exc)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, self.reconnect_max_seconds)

    async def _run_inject_only(self) -> None:
        while not self._stop.is_set():
            try:
                delta = await asyncio.wait_for(self._inject_queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            self._handle_payload(delta)

    async def stop(self) -> None:
        self._stop.set()
        if self._transport:
            await self._transport.close()

    async def _connect_and_consume(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in {"wss", "ws"}:
            raise WebSocketTransportError(f"unsupported stream scheme: {parsed.scheme}")
        host = parsed.hostname or ""
        port = parsed.port or (443 if parsed.scheme == "wss" else 80)
        path = parsed.path or DEFAULT_STREAM_PATH
        if parsed.query:
            path = f"{path}?{parsed.query}"
        headers: dict[str, str] = {}
        if self.session_token:
            headers["session-token"] = self.session_token
        transport = AsyncWebSocketTransport()
        self._transport = transport
        if parsed.scheme == "ws":
            raise WebSocketTransportError("plain ws not supported in production listener")
        await transport.connect(host, path, port=port, extra_headers=headers)
        self.stats.connected = True
        logger.info("stream listener connected to %s", url)
        try:
            while not self._stop.is_set():
                raw = await transport.recv_text()
                if raw is None:
                    break
                self.stats.messages_received += 1
                self.stats.last_message_at_ms = int(time.time() * 1000)
                self._handle_raw_message(raw)
        finally:
            self.stats.connected = False
            await transport.close()
            self._transport = None

    def _handle_raw_message(self, raw: str) -> None:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            self.stats.last_error = "invalid_json_frame"
            return
        if isinstance(payload, list):
            for item in payload:
                if isinstance(item, dict):
                    self._handle_payload(item)
            return
        if isinstance(payload, dict):
            self._handle_payload(payload)

    def _handle_payload(self, payload: dict[str, Any]) -> None:
        msg_type = str(payload.get("type") or payload.get("event") or "price_delta").lower()
        if msg_type in {"ping", "pong", "heartbeat"}:
            return
        if msg_type in {"price_delta", "book_update", "ticker", "prices"}:
            if msg_type == "prices" and isinstance(payload.get("runners"), list):
                market_id = str(payload.get("market_id") or payload.get("market-id") or "")
                ts_ms = int(payload.get("ts_ms") or time.time() * 1000)
                for runner in payload["runners"]:
                    if not isinstance(runner, dict):
                        continue
                    delta = {
                        "market_id": market_id,
                        "runner_id": runner.get("runner_id") or runner.get("runner-id") or runner.get("id"),
                        "back_odds": runner.get("back_odds") or runner.get("odds") or runner.get("price"),
                        "lay_odds": runner.get("lay_odds"),
                        "ts_ms": ts_ms,
                        "seq": payload.get("seq"),
                    }
                    if self.cache.apply_delta(delta) is not None:
                        self.stats.deltas_applied += 1
                return
            if self.cache.apply_delta(payload) is not None:
                self.stats.deltas_applied += 1
            return
        # Generic fallback: treat dict as delta when runner/market ids present
        if payload.get("runner_id") or payload.get("runner-id"):
            if self.cache.apply_delta(payload) is not None:
                self.stats.deltas_applied += 1


async def obtain_matchbook_session_token() -> str | None:
    """Best-effort REST login for WSS auth header only (not used for price polling)."""
    import os

    if not os.environ.get("MATCHBOOK_USERNAME") or not os.environ.get("MATCHBOOK_PASSWORD"):
        return None
    try:
        from hibs_racing.odds.matchbook import MatchbookClient

        client = MatchbookClient()
        try:
            return client.login()
        finally:
            client.close()
    except Exception as exc:
        logger.warning("matchbook session token unavailable for stream auth: %s", exc)
        return None
