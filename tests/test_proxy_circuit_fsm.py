"""Proxy circuit breaker FSM — Wave 2."""

from __future__ import annotations

import pytest

from inst_spine.gates.circuit import CircuitBreaker, CircuitState


def test_circuit_opens_after_failure_threshold():
    cb = CircuitBreaker(failure_threshold=3, open_cooldown_sec=60.0)
    cb.record_failure("upstream_500")
    cb.record_failure("upstream_500")
    assert cb.state == CircuitState.CLOSED
    cb.record_failure("upstream_500")
    assert cb.state == CircuitState.OPEN
    allowed, reason = cb.allows_traffic()
    assert not allowed
    assert "OPEN" in reason


def test_half_open_allows_probe(monkeypatch):
    cb = CircuitBreaker(failure_threshold=1, open_cooldown_sec=0.01)
    cb.record_failure("fail")
    assert cb.state == CircuitState.OPEN
    import time

    time.sleep(0.02)
    allowed, reason = cb.allows_traffic()
    assert allowed
    assert cb.state == CircuitState.HALF_OPEN
    assert "HALF_OPEN" in reason


def test_half_open_success_closes_circuit():
    cb = CircuitBreaker()
    cb.half_open("probe")
    cb.record_success()
    assert cb.state == CircuitState.CLOSED
    assert cb.failure_count == 0
