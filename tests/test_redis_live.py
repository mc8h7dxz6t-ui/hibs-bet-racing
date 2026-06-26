"""Live Redis profile tests — skipped when INST_REDIS_URL unset."""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("INST_REDIS_URL", "").strip(),
    reason="INST_REDIS_URL not set — live Redis profile optional",
)


@pytest.mark.asyncio
async def test_live_redis_idempotency_cas():
    import redis.asyncio as aioredis

    from inst_spine.rates import RedisIdempotencyBackend

    client = aioredis.from_url(os.environ["INST_REDIS_URL"], decode_responses=True)
    try:
        backend = RedisIdempotencyBackend(client)
        key = "instpp:live:rigorous-1"
        assert await backend.consume_idempotency_token(key, ttl_seconds=60) is True
        assert await backend.consume_idempotency_token(key, ttl_seconds=60) is False
    finally:
        await client.aclose()


def test_live_redis_drift_rolling_state(tmp_path):
    from drift_gate.state import RollingStateStore

    store = RollingStateStore.from_baseline(
        tmp_path / "unused.json",
        redis_key="instpp:live:drift-rolling",
    )
    assert store is not None
    store._data = {"features": {"x": [1.0, 2.0, 3.0]}}
    store.save()
    store2 = RollingStateStore.from_baseline(
        tmp_path / "unused.json",
        redis_key="instpp:live:drift-rolling",
    )
    assert store2 is not None
    assert (store2._data.get("features") or {}).get("x") == [1.0, 2.0, 3.0]
