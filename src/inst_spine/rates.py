"""Token bucket rate limiter and Z-score drift detector."""

from __future__ import annotations

from dataclasses import dataclass, field

from inst_spine.clocks import monotonic_seconds


@dataclass
class TokenBucket:
    """
    T_t = min(B, T_last + (t - t_last) * R)
    Reject if T_t < cost.
    """

    capacity: float
    refill_rate: float
    tokens: float | None = None
    last_refill: float | None = None

    def __post_init__(self) -> None:
        if self.tokens is None:
            self.tokens = float(self.capacity)
        if self.last_refill is None:
            self.last_refill = monotonic_seconds()

    def _replenish(self, now: float) -> None:
        assert self.tokens is not None and self.last_refill is not None
        elapsed = max(0.0, now - self.last_refill)
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now

    def consume(self, cost: float = 1.0, *, now: float | None = None) -> bool:
        """Return True if tokens consumed; False if rejected."""
        if cost <= 0:
            return True
        now = now if now is not None else monotonic_seconds()
        self._replenish(now)
        assert self.tokens is not None
        if self.tokens < cost:
            return False
        self.tokens -= cost
        return True

    def peek(self, *, now: float | None = None) -> float:
        now = now if now is not None else monotonic_seconds()
        self._replenish(now)
        assert self.tokens is not None
        return self.tokens


@dataclass
class ZScoreDriftDetector:
    """
    Z = (P_current - mu_t) / sigma_t
    Kill when |Z| > z_max.
    """

    window: int = 20
    z_max: float = 3.0
    ema_mu: float | None = None
    ema_var: float | None = None
    _alpha: float = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._alpha = 2.0 / (self.window + 1.0)

    def z_score(self, price: float) -> float | None:
        """Z against current EMA state — does not mutate."""
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
        """Ingest price; return pre-update Z if sigma > 0 else None."""
        z = self.z_score(price)
        self._ingest(price)
        return z

    def is_anomaly(self, price: float) -> tuple[bool, float | None]:
        z = self.z_score(price)
        self._ingest(price)
        if z is None:
            return False, None
        return abs(z) > self.z_max, z
