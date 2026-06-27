"""Health telemetry institutional++ tests."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from health_telemetry.export import build_health_audit_bundle, redact_entries_for_observation_lane
from health_telemetry.ingest import ingest_batch
from health_telemetry.integrate import ingest_device_batch
from health_telemetry.schema import validate_batch
from health_telemetry.sequence import DeviceSequenceStore
from inst_spine.errors import IngestValidationError
from inst_spine.rates import MemoryIdempotencyBackend


def _packets(start_seq: int = 1) -> list[dict]:
    return [
        {
            "ts": "2026-06-01T12:00:00Z",
            "seq": start_seq,
            "hr": 72,
            "spo2": 98,
        },
        {
            "ts": "2026-06-01T12:00:01Z",
            "seq": start_seq + 1,
            "hr": 73,
            "spo2": 97,
        },
    ]


def test_health_telemetry_ingest_and_chain(tmp_path: Path):
    db = tmp_path / "health.sqlite"
    entry = ingest_batch(device_id="dev-001", packets=_packets(), database=db)
    assert entry["event_type"] == "telemetry_batch"
    assert entry["coverage_pct"] == 100.0
    assert entry["sequence"]["last_seq"] == 2
    from inst_spine.ledger import AppendOnlyLedger

    assert AppendOnlyLedger(db).verify()["chain_ok"]


def test_health_telemetry_sequence_gap_fail_closed(tmp_path: Path):
    db = tmp_path / "health.sqlite"
    ingest_batch(device_id="ward-a", packets=_packets(1), database=db)
    with pytest.raises(IngestValidationError, match="gap"):
        ingest_batch(device_id="ward-a", packets=_packets(5), database=db)


def test_health_telemetry_cli_export_verify(tmp_path: Path):
    db = tmp_path / "health.sqlite"
    ingest_batch(device_id="dev-cli", packets=_packets(), database=db)
    tar = tmp_path / "health_bundle.tar"
    result = build_health_audit_bundle(db, tarball_path=tar)
    assert result.ok
    from inst_spine.product_cli import run_institutional_verify

    vcode, vbody = run_institutional_verify(tar, product="health-telemetry")
    assert vcode == 0 and vbody["ok"]


def test_health_telemetry_observation_lane_redacts_packets(tmp_path: Path):
    db = tmp_path / "health.sqlite"
    ingest_batch(device_id="dev-obs", packets=_packets(), database=db)
    from inst_spine.ledger import AppendOnlyLedger

    entries = AppendOnlyLedger(db).list_entries()
    redacted = redact_entries_for_observation_lane(entries)
    batch = next(e for e in redacted if e.get("event_type") == "telemetry_batch")
    assert "packets" not in batch["payload"]
    assert batch["payload"]["packets_redacted"] is True
    assert len(batch["payload"]["packet_summaries"]) == 2

    tar = tmp_path / "obs_bundle.tar"
    result = build_health_audit_bundle(db, tarball_path=tar, observation_lane=True)
    assert result.ok
    import tarfile

    with tarfile.open(tar, "r") as tf:
        ledger = json.loads(tf.extractfile("ledger_entries.json").read().decode())
    batch2 = next(e for e in ledger if e.get("event_type") == "telemetry_batch")
    assert "packets" not in batch2["payload"]


def test_health_telemetry_integrate_hook(tmp_path: Path):
    db = tmp_path / "health.sqlite"
    out = ingest_device_batch(device_id="hook-1", packets=_packets(), ledger_db=db)
    assert out["event_type"] == "telemetry_batch"


def test_health_telemetry_schema_full_coverage():
    assert validate_batch(_packets()) == 100.0


def test_health_telemetry_http_wal_before_ack(tmp_path: Path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    import health_telemetry.serve as serve_mod
    from inst_spine.wal import WALWriter

    db = tmp_path / "health.sqlite"
    ingress_wal = tmp_path / "health_ingress.wal"
    serve_mod.state.ledger_db = db
    serve_mod.state.wal_writer = WALWriter(ingress_wal)
    serve_mod.state.clock = serve_mod.LamportClock("test-health")
    serve_mod.state.idempotency = MemoryIdempotencyBackend()

    body = {
        "device_id": "http-ward",
        "batch_id": "batch-001",
        "packets": _packets(),
    }
    raw = json.dumps(body).encode()

    with TestClient(serve_mod.app) as client:
        r = client.post("/v1/telemetry/batch", content=raw)
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ACCEPTED"
        assert data["coverage_pct"] == 100.0

        assert ingress_wal.is_file() and ingress_wal.stat().st_size > 0
        dup = client.post("/v1/telemetry/batch", content=raw)
        assert dup.json().get("status") == "ALREADY_PROCESSED"


def test_health_telemetry_http_sequence_reject_after_wal(tmp_path: Path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    import health_telemetry.serve as serve_mod
    from inst_spine.wal import WALWriter

    db = tmp_path / "health.sqlite"
    ingress_wal = tmp_path / "health_ingress.wal"
    serve_mod.state.ledger_db = db
    serve_mod.state.wal_writer = WALWriter(ingress_wal)
    serve_mod.state.clock = serve_mod.LamportClock("test-health-reject")
    serve_mod.state.idempotency = MemoryIdempotencyBackend()

    with TestClient(serve_mod.app) as client:
        ok_body = {"device_id": "ward-gap", "batch_id": "b1", "packets": _packets(1)}
        assert client.post("/v1/telemetry/batch", json=ok_body).status_code == 200
        bad_body = {"device_id": "ward-gap", "batch_id": "b2", "packets": _packets(5)}
        r = client.post("/v1/telemetry/batch", json=bad_body)
        assert r.status_code == 422
        assert r.json().get("wal_acked") is True


def test_health_telemetry_ingest_p99_under_50ms(tmp_path: Path):
    db = tmp_path / "health.sqlite"
    store = DeviceSequenceStore.for_ledger(db)
    latencies: list[float] = []
    for i in range(100):
        start = i * 2 + 1
        t0 = time.perf_counter()
        ingest_batch(
            device_id="bench-dev",
            packets=_packets(start),
            database=db,
            sequence_db=store.database,
        )
        latencies.append((time.perf_counter() - t0) * 1000.0)
    latencies.sort()
    p99 = latencies[int(len(latencies) * 0.99) - 1]
    assert p99 < 50.0, f"p99 {p99:.3f}ms exceeds 50ms sqlite ingest target"
