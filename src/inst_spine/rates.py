"""Token bucket (pluggable storage) + Z-score drift detector."""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from inst_spine.clocks import monotonic_seconds

# Atomic token bucket via Redis EVAL (multi-instance Proxy-Risk)
_REDIS_LUA = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local cost = tonumber(ARGV[3])
local now = tonumber(ARGV[4])
local data = redis.call('HMGET', key, 'tokens', 'last_refill')
local tokens = tonumber(data[1])
local last = tonumber(data[2])
if tokens == nil then
  tokens = capacity
  last = now
end
local elapsed = math.max(0, now - last)
tokens = math.min(capacity, tokens + elapsed * refill_rate)
if tokens < cost then
  redis.call('HMSET', key, 'tokens', tokens, 'last_refill', now)
  redis.call('EXPIRE', key, 3600)
  return 0
end
tokens = tokens - cost
redis.call('HMSET', key, 'tokens', tokens, 'last_refill', now)
redis.call('EXPIRE', key, 3600)
return 1
"""


class TokenBucketBackend(ABC):
    """Pluggable storage — memory (AI Kit) or Redis (multi-instance Proxy-Risk)."""

    @abstractmethod
    def consume(self, *, key: str, capacity: float, refill_rate: float, cost: float, now: float) -> bool:
        ...

    @abstractmethod
    def peek(self, *, key: str, capacity: float, refill_rate: float, now: float) -> float:
        ...


@dataclass
class MemoryTokenBucketBackend(TokenBucketBackend):
    """Default — zero deps, single process."""

    _state: dict[str, tuple[float, float]] = field(default_factory=dict)

    def consume(self, *, key: str, capacity: float, refill_rate: float, cost: float, now: float) -> bool:
        tokens, last = self._state.get(key, (capacity, now))
        elapsed = max(0.0, now - last)
        tokens = min(capacity, tokens + elapsed * refill_rate)
        if tokens < cost:
            self._state[key] = (tokens, now)
            return False
        self._state[key] = (tokens - cost, now)
        return True

    def peek(self, *, key: str, capacity: float, refill_rate: float, now: float) -> float:
        tokens, last = self._state.get(key, (capacity, now))
        elapsed = max(0.0, now - last)
        return min(capacity, tokens + elapsed * refill_rate)


class RedisTokenBucketBackend(TokenBucketBackend):
    """Atomic multi-instance token bucket — requires redis package."""

    def __init__(self, redis_url: str, *, key_prefix: str = "inst:tb:") -> None:
        try:
            import redis
        except ImportError as exc:
            raise RuntimeError("Redis backend requires: pip install redis") from exc
        self._client = redis.from_url(redis_url, decode_responses=True)
        self._prefix = key_prefix
        self._script = self._client.register_script(_REDIS_LUA)

    def _full_key(self, key: str) -> str:
        return f"{self._prefix}{key}"

    def consume(self, *, key: str, capacity: float, refill_rate: float, cost: float, now: float) -> bool:
        result = self._script(
            keys=[self._full_key(key)],
            args=[capacity, refill_rate, cost, now],
        )
        return int(result or 0) == 1

    def peek(self, *, key: str, capacity: float, refill_rate: float, now: float) -> float:
        full = self._full_key(key)
        data = self._client.hmget(full, "tokens", "last_refill")
        tokens = float(data[0]) if data[0] is not None else capacity
        last = float(data[1]) if data[1] is not None else now
        elapsed = max(0.0, now - last)
        return min(capacity, tokens + elapsed * refill_rate)


def token_bucket_backend_from_env() -> TokenBucketBackend:
    """INST_REDIS_URL set → Redis; else memory (AI Kit default)."""
    url = os.environ.get("INST_REDIS_URL", "").strip()
    if url:
        return RedisTokenBucketBackend(url)
    return MemoryTokenBucketBackend()


@dataclass
class TokenBucket:
    """
    T_t = min(B, T_last + (t - t_last) * R)
    Uses pluggable backend for single vs multi-instance deployments.
    """

    capacity: float
    refill_rate: float
    key: str = "default"
    backend: TokenBucketBackend | None = None

    def __post_init__(self) -> None:
        if self.backend is None:
            self.backend = MemoryTokenBucketBackend()

    def consume(self, cost: float = 1.0, *, now: float | None = None) -> bool:
        if cost <= 0:
            return True
        now = now if now is not None else monotonic_seconds()
        assert self.backend is not None
        return self.backend.consume(
            key=self.key,
            capacity=self.capacity,
            refill_rate=self.refill_rate,
            cost=cost,
            now=now,
        )

    def peek(self, *, now: float | None = None) -> float:
        now = now if now is not None else monotonic_seconds()
        assert self.backend is not None
        return self.backend.peek(
            key=self.key,
            capacity=self.capacity,
            refill_rate=self.refill_rate,
            now=now,
        )


@dataclass
class ZScoreConfig:
    """Per-asset Z-score kill thresholds."""

    window: int = 20
    z_max: float = 3.0
    asset_id: str = "default"


@dataclass
class ZScoreDriftDetector:
    """Z = (P_current - mu_t) / sigma_t — kill when |Z| > z_max."""

    window: int = 20
    z_max: float = 3.0
    asset_id: str = "default"
    ema_mu: float | None = None
    ema_var: float | None = None
    _alpha: float = field(init=False, repr=False)

    @classmethod
    def from_config(cls, cfg: ZScoreConfig) -> ZScoreDriftDetector:
        return cls(window=cfg.window, z_max=cfg.z_max, asset_id=cfg.asset_id)

    def __post_init__(self) -> None:
        self._alpha = 2.0 / (self.window + 1.0)

    def z_score(self, price: float) -> float | None:
        if self.ema_mu is None or self.ema_var is None:
            return None
        sigma = self.ema_var**0.5
        if sigma <= 1e-12:
            return None
        return (price - self.ema_mu) / sigma

    def _ingest(self, price: float) -> None:
        if self.ema_mu is None:
            self.ema_mu = price
            self.ema_var = 0.0
            return
        assert self.ema_var is not None
        delta = price - self.ema_mu
        self.ema_mu = self._alpha * price + (1.0 - self._alpha) * self.ema_mu
        self.ema_var = (1.0 - self._alpha) * (self.ema_var + self._alpha * delta * delta)

    def update(self, price: float) -> float | None:
        z = self.z_score(price)
        self._ingest(price)
        return z

    def is_anomaly(self, price: float) -> tuple[bool, float | None]:
        z = self.z_score(price)
        self._ingest(price)
        if z is None:
            return False, None
        return abs(z) > self.z_max, z


# --- Atomic idempotency mesh (Redis Lua CAS / memory) ---

_REDIS_IDEMPOTENCY_LUA = """
local exists = redis.call('EXISTS', KEYS[1])
if exists == 1 then
    return 0
else
    redis.call('SET', KEYS[1], '1')
    redis.call('EXPIRE', KEYS[1], ARGV[1])
    return 1
end
"""


class IdempotencyBackend(ABC):
    """Distributed deduplication — True if unique token registered."""

    @abstractmethod
    async def consume_idempotency_token(self, key: str, ttl_seconds: int) -> bool:
        """
        Return True if payload token is unique and registered.
        Return False if already processed within TTL.
        """


class MemoryIdempotencyBackend(IdempotencyBackend):
    """Single-process fallback — monotonic expiry ticks."""

    def __init__(self) -> None:
        self._storage: dict[str, float] = {}

    async def consume_idempotency_token(self, key: str, ttl_seconds: int) -> bool:
        now = monotonic_seconds()
        exp = self._storage.get(key)
        if exp is not None and exp >= now:
            return False
        if exp is not None:
            del self._storage[key]
        self._storage[key] = now + float(ttl_seconds)
        return True


class RedisIdempotencyBackend(IdempotencyBackend):
    """Atomic Redis Lua CAS — multi-instance webhook mesh."""

    def __init__(self, redis_client: Any, *, key_prefix: str = "inst:idemp:") -> None:
        self.redis = redis_client
        self._prefix = key_prefix
        self._script = self.redis.register_script(_REDIS_IDEMPOTENCY_LUA)

    def _full_key(self, key: str) -> str:
        return f"{self._prefix}{key}"

    async def consume_idempotency_token(self, key: str, ttl_seconds: int) -> bool:
        import logging

        logger = logging.getLogger("inst-spine.rates")
        try:
            result = await self._script(keys=[self._full_key(key)], args=[ttl_seconds])
            return bool(int(result or 0) == 1)
        except Exception as exc:
            logger.critical(
                "IDEMPOTENCY_BACKEND_DISRUPTED: key %s failed (%s) — fail-closed",
                key,
                exc,
            )
            return False


def idempotency_backend_from_env(*, redis_client: Any | None = None) -> IdempotencyBackend:
    """INST_REDIS_URL → async Redis CAS; else in-memory."""
    if redis_client is not None:
        return RedisIdempotencyBackend(redis_client)
    url = os.environ.get("INST_REDIS_URL", "").strip()
    if url:
        try:
            import redis.asyncio as aioredis
        except ImportError as exc:
            raise RuntimeError("Redis idempotency requires: pip install redis") from exc
        client = aioredis.from_url(url, encoding="utf-8", decode_responses=True)
        return RedisIdempotencyBackend(client)
    return MemoryIdempotencyBackend()
