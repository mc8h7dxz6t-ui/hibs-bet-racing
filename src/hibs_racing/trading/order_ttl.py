"""In-play venue order TTL guard — 450ms authoritative-ack cancel contract."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from hibs_racing.trading.config import liquidity_router_active

logger = logging.getLogger(__name__)

INPLAY_ORDER_TTL_MS = 450
INPLAY_ORDER_TIMED_OUT_ABORT = "INPLAY_ORDER_TIMED_OUT_ABORT"


class InPlayOrderPathMuted(RuntimeError):
    """Raised when TTL abort has muted the venue order path."""


CancelFn = Callable[[dict[str, Any]], None]
SubmitFn = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass
class InPlayOrderTracker:
    """Tracks outstanding venue requests and fires non-blocking TTL cancels."""

    ttl_ms: int = INPLAY_ORDER_TTL_MS
    _muted_paths: set[str] = field(default_factory=set)
    _pending: dict[str, asyncio.Task] = field(default_factory=dict)

    def attach_expiry(self, request: dict[str, Any], *, now_ms: float | None = None) -> dict[str, Any]:
        now = now_ms if now_ms is not None else time.time() * 1000
        req = dict(request)
        req.setdefault("client_order_id", str(uuid.uuid4()))
        req["submitted_at_ms"] = int(now)
        req["expires_at_epoch_ms"] = int(now + self.ttl_ms)
        return req

    def is_muted(self, channel: str) -> bool:
        return channel in self._muted_paths

    async def submit_with_ttl(
        self,
        *,
        channel: str,
        request: dict[str, Any],
        submit_fn: SubmitFn,
        cancel_fn: CancelFn,
        confirm_fn: Callable[[dict[str, Any]], bool] | None = None,
        log_abort: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        if self.is_muted(channel):
            raise InPlayOrderPathMuted(f"order path muted for channel={channel}")

        req = self.attach_expiry(request)
        order_id = str(req["client_order_id"])
        ack: dict[str, Any] | None = None
        ack_event = asyncio.Event()

        async def _wait_ack() -> None:
            nonlocal ack
            try:
                ack = await asyncio.to_thread(submit_fn, req)
                if confirm_fn is None or confirm_fn(ack):
                    ack_event.set()
            except Exception as exc:
                ack = {"ok": False, "error": str(exc)}

        submit_task = asyncio.create_task(_wait_ack())
        try:
            await asyncio.wait_for(ack_event.wait(), timeout=self.ttl_ms / 1000.0)
        except asyncio.TimeoutError:
            self._muted_paths.add(channel)
            abort_payload = {
                "signal": INPLAY_ORDER_TIMED_OUT_ABORT,
                "channel": channel,
                "client_order_id": order_id,
                "expires_at_epoch_ms": req["expires_at_epoch_ms"],
                "ttl_ms": self.ttl_ms,
                "request": req,
            }
            if log_abort is not None:
                log_abort(abort_payload)
            else:
                logger.warning("%s channel=%s order=%s", INPLAY_ORDER_TIMED_OUT_ABORT, channel, order_id[:8])
            asyncio.create_task(asyncio.to_thread(cancel_fn, req))
            await asyncio.sleep(0)
            return {
                "ok": False,
                "status": INPLAY_ORDER_TIMED_OUT_ABORT,
                "channel": channel,
                "client_order_id": order_id,
                "muted": True,
            }
        finally:
            if not submit_task.done():
                submit_task.cancel()

        return {
            "ok": True,
            "status": "VENUE_ACK",
            "channel": channel,
            "client_order_id": order_id,
            "ack": ack or {},
        }


def default_cancel_fn(request: dict[str, Any]) -> None:
    """Non-blocking async cancel stub — exchange API surface."""
    if not liquidity_router_active():
        return
    logger.info("async venue cancel client_order_id=%s", str(request.get("client_order_id"))[:8])


def log_timed_out_abort_to_ledger(payload: dict[str, Any]) -> None:
    try:
        from hibs_racing.institutional.ledger_events import append_ledger_event

        append_ledger_event(
            event_type=INPLAY_ORDER_TIMED_OUT_ABORT,
            payload=payload,
            runner_id=str((payload.get("request") or {}).get("runner_id") or "") or None,
        )
    except Exception as exc:
        logger.warning("ledger abort log failed: %s", exc)
