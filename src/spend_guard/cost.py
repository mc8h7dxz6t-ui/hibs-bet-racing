"""Token cost estimation for OpenAI-compatible spend gateway."""

from __future__ import annotations

import os
from typing import Any

# Micro-dollars per 1K tokens (input, output) — conservative reserve estimates.
_MODEL_RATES: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4": (30.0, 60.0),
    "claude-3-5-sonnet": (3.0, 15.0),
    "gemini-1.5-flash": (0.075, 0.30),
    "demo-model": (0.10, 0.10),
}
_DEFAULT_RATE = (0.50, 1.50)
_CHARS_PER_TOKEN = 4.0


def _rates_for_model(model: str) -> tuple[float, float]:
    key = (model or "").strip().lower()
    for name, rates in _MODEL_RATES.items():
        if key == name or key.startswith(name):
            return rates
    return _DEFAULT_RATE


def estimate_reserve_cost(body: dict[str, Any]) -> tuple[float, str]:
    """Upper-bound reserve from model + max_tokens (fail-safe for buyer wallet)."""
    model = str(body.get("model") or os.getenv("SPEND_GUARD_DEFAULT_MODEL", "gpt-4o-mini"))
    max_tokens = int(body.get("max_tokens") or body.get("max_completion_tokens") or 256)
    messages = body.get("messages") or []
    prompt_chars = sum(len(str(m.get("content", ""))) for m in messages if isinstance(m, dict))
    prompt_tokens = max(1, int(prompt_chars / _CHARS_PER_TOKEN))
    input_rate, output_rate = _rates_for_model(model)
    # Reserve on worst-case output at max_tokens + prompt input.
    cost = (prompt_tokens / 1000.0) * input_rate + (max_tokens / 1000.0) * output_rate
    reserve = max(0.001, round(cost * float(os.getenv("SPEND_GUARD_RESERVE_BUFFER", "1.15")), 6))
    return reserve, model


def actual_cost_from_usage(usage: dict[str, Any] | None, *, model: str) -> float:
    """Settle from upstream usage block when present."""
    if not usage:
        return 0.0
    input_rate, output_rate = _rates_for_model(model)
    prompt = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
    completion = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
    cost = (prompt / 1000.0) * input_rate + (completion / 1000.0) * output_rate
    return max(0.0, round(cost, 6))
