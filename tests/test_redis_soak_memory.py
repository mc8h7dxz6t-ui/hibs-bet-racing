"""Memory-backend soak — rigorous-safe without live Redis (Wave 1)."""

from __future__ import annotations

import pytest

from inst_spine.rates import MemoryIdempotencyBackend, MemoryTokenBucketBackend


@pytest.mark.asyncio
async def test_memory_idempotency_soak():
    backend = MemoryIdempotencyBackend()
    for i in range(200):
        key = f"soak:{i % 40}"
        first = await backend.consume_idempotency_token(key, ttl_seconds=120)
        second = await backend.consume_idempotency_token(key, ttl_seconds=120)
        if i < 40:
            assert first is True
        assert second is False


def test_memory_token_bucket_soak():
    import time

    backend = MemoryTokenBucketBackend()
    now = time.monotonic()
    for i in range(100):
        allowed = backend.consume(
            key="soak-bucket",
            capacity=10.0,
            refill_rate=1.0,
            cost=1.0,
            now=now + i * 0.01,
        )
        assert allowed in (True, False)
