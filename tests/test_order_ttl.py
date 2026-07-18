"""TTL cancel contract tests for in-play liquidity router."""

from __future__ import annotations

import asyncio
import time

import pytest

from hibs_racing.trading.order_ttl import (
    INPLAY_ORDER_TIMED_OUT_ABORT,
    INPLAY_ORDER_TTL_MS,
    InPlayOrderTracker,
)


@pytest.mark.asyncio
async def test_ttl_abort_mutes_path_and_fires_cancel():
    tracker = InPlayOrderTracker(ttl_ms=50)
    cancels: list[dict] = []
    aborts: list[dict] = []

    def slow_submit(_req: dict) -> dict:
        time.sleep(0.2)
        return {"authoritative": True}

    result = await tracker.submit_with_ttl(
        channel="matchbook",
        request={"runner_id": "1", "odds": 5.0, "stake": 10.0},
        submit_fn=slow_submit,
        cancel_fn=lambda req: cancels.append(req),
        confirm_fn=lambda ack: bool(ack.get("authoritative")),
        log_abort=lambda payload: aborts.append(payload),
    )
    assert result["status"] == INPLAY_ORDER_TIMED_OUT_ABORT
    assert tracker.is_muted("matchbook")
    await asyncio.sleep(0.05)
    assert cancels
    assert aborts[0]["signal"] == INPLAY_ORDER_TIMED_OUT_ABORT


def test_request_carries_expiry_epoch():
    tracker = InPlayOrderTracker(ttl_ms=INPLAY_ORDER_TTL_MS)
    req = tracker.attach_expiry({"odds": 3.0}, now_ms=1_000_000.0)
    assert req["expires_at_epoch_ms"] == 1_000_000 + INPLAY_ORDER_TTL_MS
    assert "client_order_id" in req
