"""Structured output validation gate."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, TypeVar

T = TypeVar("T")


@dataclass
class ValidationResult:
    ok: bool
    value: Any | None
    error: str | None
    attempts: int


def validate_with_retry(
    raw: str,
    validator: Callable[[dict[str, Any]], T],
    *,
    max_attempts: int = 3,
) -> ValidationResult:
    """Parse JSON and validate — retry caller supplies new raw on failure."""
    last_err = ""
    for attempt in range(1, max_attempts + 1):
        try:
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError("expected JSON object")
            val = validator(data)
            return ValidationResult(ok=True, value=val, error=None, attempts=attempt)
        except Exception as exc:
            last_err = str(exc)
    return ValidationResult(ok=False, value=None, error=last_err, attempts=max_attempts)
