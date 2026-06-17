"""Logical and monotonic clocks — wall time is metadata only."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def monotonic_seconds() -> float:
    """Elapsed seconds from CLOCK_MONOTONIC — never moves backward."""
    return time.monotonic()


def utc_now_iso() -> str:
    """Wall clock for human audit — not used for chain integrity."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class LamportClock:
    """Per-writer Lamport counter for causal ordering."""

    writer_id: str
    _counter: int = 0

    def tick(self) -> int:
        self._counter += 1
        return self._counter

    def observe(self, other_seq: int) -> int:
        self._counter = max(self._counter, other_seq) + 1
        return self._counter

    @property
    def value(self) -> int:
        return self._counter


@dataclass
class VectorClock:
    """Multi-writer causal ordering."""

    writer_id: str
    vector: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.vector.setdefault(self.writer_id, 0)

    def tick(self) -> dict[str, int]:
        self.vector[self.writer_id] = self.vector.get(self.writer_id, 0) + 1
        return dict(self.vector)

    def observe(self, other: dict[str, int]) -> dict[str, int]:
        keys = set(self.vector) | set(other)
        merged = {k: max(self.vector.get(k, 0), other.get(k, 0)) for k in keys}
        merged[self.writer_id] = merged.get(self.writer_id, 0) + 1
        self.vector = merged
        return dict(self.vector)

    def happens_before(self, other: dict[str, int]) -> bool:
        if not other:
            return False
        leq = all(self.vector.get(k, 0) <= other.get(k, 0) for k in other)
        strict = any(self.vector.get(k, 0) < other.get(k, 0) for k in other)
        return leq and strict

    def to_dict(self) -> dict[str, Any]:
        return dict(self.vector)
