"""Inst++ spine — hash chain, rates, clocks, ledger, gates."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from inst_spine.clocks import LamportClock, VectorClock, monotonic_seconds
from inst_spine.gates.circuit import CircuitBreaker
from inst_spine.gates.engine import GateEngine
from inst_spine.hash import GENESIS_HASH, chain_hash, verify_chain, verify_lamport_monotonic
from inst_spine.ledger import AppendOnlyLedger, IdempotencyGuard
from inst_spine.rates import TokenBucket, ZScoreDriftDetector


def test_lamport_monotonic():
    clk = LamportClock("w1")
    a, b, c = clk.tick(), clk.tick(), clk.tick()
    assert a < b < c


def test_vector_clock_causal():
    va = VectorClock("a")
    vb = VectorClock("b")
    va.tick()
    snap = va.to_dict()
    vb.observe(snap)
    vb.tick()
    assert vb.vector["b"] >= 1


def test_monotonic_never_backward():
    t0 = monotonic_seconds()
    t1 = monotonic_seconds()
    assert t1 >= t0


def test_chain_hash_links_prev():
    h1 = chain_hash(payload={"a": 1}, prev_hash=GENESIS_HASH, lamport_seq=1)
    h2 = chain_hash(payload={"a": 2}, prev_hash=h1, lamport_seq=2)
    assert h1 != h2
    rows = [
        {"payload": {"a": 1}, "lamport_seq": 1, "prev_hash": GENESIS_HASH, "entry_hash": h1, "metadata": {}},
        {"payload": {"a": 2}, "lamport_seq": 2, "prev_hash": h1, "entry_hash": h2, "metadata": {}},
    ]
    assert verify_chain(rows).ok


def test_chain_detects_tamper():
    h1 = chain_hash(payload={"a": 1}, prev_hash=GENESIS_HASH, lamport_seq=1)
    rows = [
        {"payload": {"a": 1}, "lamport_seq": 1, "prev_hash": GENESIS_HASH, "entry_hash": "deadbeef" * 8, "metadata": {}},
    ]
    result = verify_chain(rows)
    assert not result.ok
    assert result.first_mismatch_index == 0


def test_token_bucket_burst_then_sustain():
    b = TokenBucket(capacity=5.0, refill_rate=1.0, tokens=5.0, last_refill=0.0)
    for _ in range(5):
        assert b.consume(1.0, now=1.0)
    assert not b.consume(1.0, now=1.0)
    assert b.consume(1.0, now=3.0)


def test_zscore_triggers_anomaly():
    d = ZScoreDriftDetector(window=5, z_max=2.0)
    for p in [100.0, 100.1, 99.9, 100.0, 100.2, 100.1, 99.8]:
        d.update(p)
    anomaly, z = d.is_anomaly(150.0)
    assert anomaly
    assert z is not None


def test_ledger_append_and_verify(tmp_path: Path):
    db = tmp_path / "ledger.sqlite"
    ledger = AppendOnlyLedger(db, writer_id="test")
    ledger.append(event_type="e1", payload={"x": 1}, manifest_id="m1")
    ledger.append(event_type="e2", payload={"x": 2}, manifest_id="m1")
    v = ledger.verify()
    assert v["chain_ok"]
    assert v["lamport_monotonic"]


def test_ledger_async_write_behind(tmp_path: Path):
    db = tmp_path / "async.sqlite"
    ledger = AppendOnlyLedger(db, writer_id="async", async_writes=True)
    ledger.start_async_writer()
    for i in range(20):
        ledger.append(event_type="evt", payload={"i": i})
    flushed = ledger.flush()
    assert flushed >= 0
    ledger.stop_async_writer()
    assert ledger.verify()["chain_ok"]


def test_idempotency_guard():
    g = IdempotencyGuard(ttl_sec=60.0)
    assert g.check_and_set("k1", now=0.0)
    assert not g.check_and_set("k1", now=1.0)
    assert g.check_and_set("k1", now=61.0)


def test_circuit_kill():
    cb = CircuitBreaker()
    cb.kill("test")
    ok, _ = cb.allows_traffic()
    assert not ok


def test_f_gates_with_ledger(tmp_path: Path):
    db = tmp_path / "gates.sqlite"
    ledger = AppendOnlyLedger(db)
    ledger.append(event_type="d", payload={"ok": True}, manifest_id="m")
    entries = ledger.list_entries()
    engine = GateEngine()
    passed, results = engine.all_passed(
        {
            "ledger_entries": entries,
            "expected_count": 1,
            "actual_count": 1,
            "source_coverage_pct": 100.0,
        }
    )
    assert passed
    assert len(results) == 9
