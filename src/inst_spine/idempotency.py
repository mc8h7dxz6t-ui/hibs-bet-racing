"""Tri-state idempotency outcomes — fail-closed on backend disruption."""

from __future__ import annotations

from enum import Enum


class IdempotencyOutcome(str, Enum):
    """Result of atomic idempotency CAS — never conflate DUPLICATE with BACKEND_ERROR."""

    UNIQUE = "unique"
    DUPLICATE = "duplicate"
    BACKEND_ERROR = "backend_error"

    @property
    def is_unique(self) -> bool:
        return self is IdempotencyOutcome.UNIQUE

    @property
    def is_duplicate(self) -> bool:
        return self is IdempotencyOutcome.DUPLICATE

    @property
    def is_backend_error(self) -> bool:
        return self is IdempotencyOutcome.BACKEND_ERROR
