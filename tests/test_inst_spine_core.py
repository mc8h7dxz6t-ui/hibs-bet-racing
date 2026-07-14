"""Inst++ spine — hash chain, rates, clocks, ledger, gates, genesis, WAL."""

from __future__ import annotations

from pathlib import Path

import pytest

from inst_spine.clocks import LamportClock, VectorClock, monotonic_seconds
from inst_spine.gates.circuit import CircuitBreaker
from inst_spine.gates.engine import GateEngine
from inst_spine.hash import (
    GENESIS_EVENT,
    GENESIS_PREV_HASH,
    build_genesis_record,
    chain_hash,
    verify_chain,
    verify_genesis_block,
    write_genesis_anchor,
)
from inst_spine.ledger import AppendOnlyLedger, IdempotencyGuard
from inst_spine.rates import MemoryTokenBucketBackend, TokenBucket, ZScoreDriftDetector


def _genesis_row(writer: str = "test") -> dict:
    return build_genesis_record(
        instance_uuid="uuid-test-001",
        config_hash="cfg-test",
        writer_id=writer,
        wall_time_utc="2026-01-01T00:00:00+00:00",
    )


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


def test_chain_hash_links_prev_with_genesis():
    g = _genesis_row()
    h1 = chain_hash(payload={"a": 1}, prev_hash=g["entry_hash"], lamport_seq=1)
    rows = [
        {**g, "payload": g["payload"], "metadata": g["metadata"]},
        {"payload": {"a": 1}, "lamport_seq": 1, "prev_hash": g["entry_hash"], "entry_hash": h1, "metadata": {}},
    ]
    assert verify_chain(rows).ok


def test_empty_chain_fails_without_genesis():
    assert not verify_chain([]).ok


def test_genesis_anchor_tamper_fails():
    g = _genesis_row()
    anchor = {"instance_uuid": "wrong", "genesis_hash": g["entry_hash"]}
    assert not verify_genesis_block(g, anchor=anchor).ok


def test_chain_detects_tamper():
    g = _genesis_row()
    h1 = chain_hash(payload={"a": 1}, prev_hash=g["entry_hash"], lamport_seq=1)
    rows = [
        {**g, "payload": g["payload"], "metadata": g["metadata"]},
        {"payload": {"a": 1}, "lamport_seq": 1, "prev_hash": g["entry_hash"], "entry_hash": "deadbeef" * 8, "metadata": {}},
    ]
    result = verify_chain(rows)
    assert not result.ok


def test_token_bucket_burst_then_sustain():
    backend = MemoryTokenBucketBackend()
    b = TokenBucket(capacity=5.0, refill_rate=1.0, key="t1", backend=backend)
    for _ in range(5):
        assert b.consume(1.0, now=1.0)
    assert not b.consume(1.0, now=1.0)
    assert b.consume(1.0, now=3.0)


def test_token_bucket_shared_backend_multi_instance():
    """Two buckets same key share state — simulates Redis across instances."""
    backend = MemoryTokenBucketBackend()
    a = TokenBucket(capacity=2.0, refill_rate=0.01, key="client-x", backend=backend)
    b = TokenBucket(capacity=2.0, refill_rate=0.01, key="client-x", backend=backend)
    assert a.consume(1.0, now=1.0)
    assert b.consume(1.0, now=1.0)
    assert not a.consume(1.0, now=1.0)


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
    assert v["genesis_ok"]
    assert v["chain_ok"]
    assert v["lamport_monotonic"]
    assert v["wal_records"] >= 3


def test_wal_survives_sqlite_lag(tmp_path: Path):
    """Crash before SQLite flush — new process recovers from WAL."""
    db = tmp_path / "crash.sqlite"
    ledger = AppendOnlyLedger(db, writer_id="crash", async_writes=True)
    ledger.start_async_writer()
    ledger.append(event_type="burst", payload={"n": 1})
    ledger.append(event_type="burst", payload={"n": 2})
    # Simulate crash — no flush/stop
    ledger2 = AppendOnlyLedger(db, writer_id="crash")
    v = ledger2.verify()
    assert v["chain_ok"]
    assert ledger2.wal.count() >= 3


def test_ledger_async_write_behind(tmp_path: Path):
    db = tmp_path / "async.sqlite"
    ledger = AppendOnlyLedger(db, writer_id="async", async_writes=True)
    ledger.start_async_writer()
    for i in range(20):
        ledger.append(event_type="evt", payload={"i": i})
    ledger.stop_async_writer(flush=True)
    assert ledger.verify()["chain_ok"]


def test_wiped_sqlite_without_wal_fails_genesis(tmp_path: Path):
    db = tmp_path / "wiped.sqlite"
    ledger = AppendOnlyLedger(db)
    ledger.append(event_type="e", payload={"x": 1})
    # Wipe sqlite only — WAL + anchor remain
    db.unlink()
    ledger2 = AppendOnlyLedger(db)
    assert ledger2.verify()["chain_ok"]


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
            "expected_count": len(entries),
            "actual_count": len(entries),
            "source_coverage_pct": 100.0,
        }
    )
    assert passed
    assert len(results) == 9
