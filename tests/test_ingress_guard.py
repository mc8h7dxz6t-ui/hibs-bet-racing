"""Ingress guard + idempotency tri-state tests."""

from __future__ import annotations

import pytest

from inst_spine.idempotency import IdempotencyOutcome
from inst_spine.ingress_guard import validate_forward_url
from inst_spine.rates import MemoryIdempotencyBackend


@pytest.mark.asyncio
async def test_idempotency_tri_state():
    backend = MemoryIdempotencyBackend()
    assert await backend.consume_idempotency_token("k1", 60) is IdempotencyOutcome.UNIQUE
    assert await backend.consume_idempotency_token("k1", 60) is IdempotencyOutcome.DUPLICATE


def test_ssrf_blocks_private_host():
    ok, reason = validate_forward_url("http://127.0.0.1/hook")
    assert not ok
    assert "blocked" in reason or "http_forward" in reason


def test_ssrf_allows_https_public(monkeypatch):
    monkeypatch.delenv("WEBHOOK_FORWARD_ALLOWLIST", raising=False)
    ok, reason = validate_forward_url("https://hooks.example.com/stripe")
    assert ok, reason
