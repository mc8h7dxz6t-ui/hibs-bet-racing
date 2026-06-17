"""Token bucket per provider — wraps inst_spine.rates."""

from __future__ import annotations

from dataclasses import dataclass, field

from inst_spine.rates import TokenBucket


@dataclass
class ProviderRateLimiter:
    """Per (provider, model) token buckets."""

    default_capacity: float = 60.0
    default_refill: float = 1.0
    _buckets: dict[str, TokenBucket] = field(default_factory=dict)

    def _key(self, provider: str, model: str) -> str:
        return f"{provider}:{model}"

    def bucket_for(self, provider: str, model: str) -> TokenBucket:
        key = self._key(provider, model)
        if key not in self._buckets:
            self._buckets[key] = TokenBucket(
                capacity=self.default_capacity,
                refill_rate=self.default_refill,
            )
        return self._buckets[key]

    def acquire(self, provider: str, model: str, *, cost: float = 1.0) -> bool:
        return self.bucket_for(provider, model).consume(cost)

    def wait_hint_seconds(self, provider: str, model: str, *, cost: float = 1.0) -> float:
        b = self.bucket_for(provider, model)
        available = b.peek()
        if available >= cost:
            return 0.0
        deficit = cost - available
        return deficit / b.refill_rate if b.refill_rate > 0 else 1.0
