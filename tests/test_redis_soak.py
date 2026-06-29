"""Redis soak — production profile stress (requires INST_REDIS_URL)."""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("INST_REDIS_URL", "").strip(),
    reason="INST_REDIS_URL not set",
)

SOAK_ITERATIONS = int(os.environ.get("INST_REDIS_SOAK_ITERATIONS", "200"))


@pytest.mark.asyncio
async def test_redis_idempotency_soak():
    import redis.asyncio as aioredis

    from inst_spine.rates import RedisIdempotencyBackend

    client = aioredis.from_url(os.environ["INST_REDIS_URL"], decode_responses=True)
    backend = RedisIdempotencyBackend(client)
    try:
        for i in range(SOAK_ITERATIONS):
            key = f"instpp:soak:idempotency:{i % 50}"
            first = await backend.consume_idempotency_token(key, ttl_seconds=120)
            second = await backend.consume_idempotency_token(key, ttl_seconds=120)
            if i < 50:
                assert first is True
            assert second is False
    finally:
        await client.aclose()


def test_redis_drift_rolling_soak(tmp_path):
    from drift_gate.state import RollingStateStore

    base = tmp_path / "soak_baseline.json"
    base.write_text('{"features": {"x": [1.0]}}', encoding="utf-8")
    key = "instpp:soak:drift-rolling"
    for i in range(SOAK_ITERATIONS):
        store = RollingStateStore.from_baseline(base, redis_key=key)
        assert store is not None
        store._data = {"x": [float(i), float(i + 1)]}
        store.save()
        store2 = RollingStateStore.from_baseline(base, redis_key=key)
        assert store2 is not None
        assert store2._data.get("x") == [float(i), float(i + 1)]
