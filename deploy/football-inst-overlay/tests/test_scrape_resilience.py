"""Tests for scrape resilience (circuit breaker, ledger, resilient_call)."""

from __future__ import annotations

import pytest


def test_circuit_opens_after_failures(monkeypatch, tmp_path):
    monkeypatch.setenv("HIBS_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("HIBS_SCRAPE_CIRCUIT_FAILURES", "2")
    from hibs_predictor.scrapers import scrape_resilience as sr

    sr._circuits.clear()

    def boom():
        raise RuntimeError("blocked")

    with pytest.raises(RuntimeError):
        sr.resilient_call("test_src", boom, max_retries=1)
    with pytest.raises(RuntimeError):
        sr.resilient_call("test_src", boom, max_retries=1)

    circuit = sr.get_circuit("test_src")
    allows, reason = circuit.allows_traffic()
    assert allows is False
    assert "circuit_open" in reason


def test_resilient_call_success_records_ledger(monkeypatch, tmp_path):
    monkeypatch.setenv("HIBS_CACHE_DIR", str(tmp_path))
    from hibs_predictor.scrapers import scrape_resilience as sr

    sr._circuits.clear()
    out = sr.resilient_call("ok_src", lambda: 42, max_retries=1)
    assert out == 42
    summary = sr.ledger_summary()
    assert summary["entries"] >= 1
    assert summary["sources"].get("ok_src", {}).get("ok", 0) >= 1


def test_scrape_resilience_status_shape(monkeypatch, tmp_path):
    monkeypatch.setenv("HIBS_CACHE_DIR", str(tmp_path))
    from hibs_predictor.scrapers.scrape_resilience import scrape_resilience_status

    st = scrape_resilience_status()
    assert st["ok"] is True
    assert "circuits" in st
    assert "ledger" in st
