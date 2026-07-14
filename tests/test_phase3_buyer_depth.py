"""Phase 3 — buyer-specific depth + diligence automation (SKU CI only)."""

from __future__ import annotations

import json
import tarfile
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from altdata.feed_schema import feed_schema_registry
from altdata.ladders import FIELD_LADDERS
from inst_spine.errors import IngestValidationError
from inst_spine.export import build_audit_bundle, verify_audit_bundle
from inst_spine.ledger import AppendOnlyLedger
from model_governor.integrity import compute_artifact_digest, validate_artifact_hash


def _model_snapshot_with_valid_hash(**overrides) -> dict:
    base = {
        "model_id": "rigorous-m3",
        "version": "1.0.0",
        "risk_tier": "medium",
        "framework": "demo",
        "metrics": {"auc": 0.9},
    }
    base.update(overrides)
    digest = compute_artifact_digest({**base, "artifact_hash": "pending"})
    base["artifact_hash"] = f"sha256:{digest}"
    return base


def test_model_governor_artifact_hash_mismatch_rejected():
    snap = _model_snapshot_with_valid_hash()
    snap["artifact_hash"] = "sha256:deadbeef"
    with pytest.raises(IngestValidationError, match="artifact_hash mismatch"):
        validate_artifact_hash(snap)


def test_model_governor_record_rejects_tampered_hash(tmp_path: Path):
    from model_governor.record import record_governance_event

    db = tmp_path / "mg.sqlite"
    snap = _model_snapshot_with_valid_hash()
    record_governance_event(action="register", model_snapshot=snap, database=db)
    bad = dict(snap)
    bad["artifact_hash"] = "sha256:0000000000000000000000000000000000000000000000000000000000000000"
    with pytest.raises(IngestValidationError, match="artifact_hash mismatch"):
        record_governance_event(action="approve", model_snapshot=bad, database=db)


def test_altdata_per_feed_schema_template():
    reg = feed_schema_registry()
    for feed_id, ladder in FIELD_LADDERS.items():
        assert feed_id in reg["feeds"]
        assert reg["feeds"][feed_id]["field_count"] == len(ladder)


def test_altdata_production_feed_registry_slot():
    from altdata.feeds import PRODUCTION_FEEDS, list_production_feeds

    feeds = list_production_feeds()
    assert "fx_gbp_cross" in PRODUCTION_FEEDS
    assert any(f["feed_id"] == "fx_gbp_cross" for f in feeds)


def test_health_observation_lane_verify_bundle(tmp_path: Path):
    from health_telemetry.ingest import ingest_batch

    db = tmp_path / "health.sqlite"
    packets = [
        {"ts": "2026-06-01T12:00:00Z", "seq": 1, "hr": 72, "spo2": 98},
    ]
    ingest_batch(device_id="obs-dev", packets=packets, database=db)
    tar = tmp_path / "health_obs.tar"
    from health_telemetry.export import build_health_audit_bundle

    result = build_health_audit_bundle(db, tarball_path=tar, observation_lane=True)
    assert result.ok is True
    from inst_spine.export import verify_audit_bundle

    verify = verify_audit_bundle(tar)
    assert verify.ok is True
    with tarfile.open(tar, "r") as tf:
        entries = json.loads(tf.extractfile("ledger_entries.json").read().decode())
    traces = [e for e in entries if e.get("event_type") == "telemetry_batch"]
    assert traces and all("packets" not in (e.get("payload") or {}) for e in traces)


def test_health_http_device_auth_ingress(tmp_path: Path, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from inst_spine.clocks import LamportClock
    from inst_spine.rates import MemoryIdempotencyBackend
    from inst_spine.middleware import device_token_hmac
    from inst_spine.wal import WALWriter

    db = tmp_path / "health.sqlite"
    monkeypatch.setenv("HEALTH_TELEMETRY_DB", str(db))
    monkeypatch.setenv("HEALTH_DEVICE_AUTH_SECRET", "phase3-secret")
    monkeypatch.setenv("INST_REQUIRE_DEVICE_AUTH", "1")

    import health_telemetry.serve as mod

    mod.state.ledger_db = db
    mod.state.wal_writer = WALWriter(tmp_path / "health.wal")
    mod.state.clock = LamportClock("phase3-health")
    mod.state.idempotency = MemoryIdempotencyBackend()
    token = device_token_hmac("ward-p3", secret="phase3-secret")
    pkt = {"ts": "2026-01-01T00:00:00Z", "seq": 1, "rpm": 72, "spo2": 98, "hr": 72}

    with TestClient(mod.app) as client:
        ready = client.get("/ready").json()
        assert ready["checks"]["device_auth"]["ok"] is True
        r = client.post(
            "/v1/telemetry/batch",
            json={"device_id": "ward-p3", "packets": [pkt]},
            headers={"X-Device-Token": "bad"},
        )
        assert r.status_code == 401
        r2 = client.post(
            "/v1/telemetry/batch",
            json={"device_id": "ward-p3", "packets": [pkt], "batch_id": "p3"},
            headers={"X-Device-Token": token},
        )
        assert r2.status_code == 200


def test_compliance_mtls_ingest(tmp_path: Path, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    db = tmp_path / "compliance.sqlite"
    monkeypatch.setenv("COMPLIANCE_LOGGER_DATABASE", str(db))
    monkeypatch.delenv("COMPLIANCE_LOGGER_API_KEY", raising=False)
    monkeypatch.setenv("INST_MTLS_REQUIRED", "1")
    monkeypatch.setenv("INST_MTLS_ALLOWED_CN", "auditor-client")

    import compliance_log.serve as serve_mod

    serve_mod.state.database = str(db)
    body = {"snapshot": {"id": "mtls-1"}, "outcome": {"ok": True}}

    with TestClient(serve_mod.app) as client:
        r = client.post("/v1/decisions", json=body)
        assert r.status_code == 401
        r2 = client.post(
            "/v1/decisions",
            json=body,
            headers={"X-Client-Cert-CN": "auditor-client"},
        )
        assert r2.status_code == 200


def test_ai_kit_step_fn_exception_fail_closed(tmp_path: Path):
    from ai_kit.pipeline import AgentLoop

    trace = AppendOnlyLedger(tmp_path / "trace.sqlite")
    loop = AgentLoop(agent_id="p3", checkpoint_db=tmp_path / "cp.sqlite", trace_ledger=trace)

    def boom(_step: int, state: dict) -> dict:
        raise RuntimeError("buyer step_fn failed")

    with pytest.raises(RuntimeError, match="buyer step_fn failed"):
        loop.run_steps(start_step=0, steps=1, step_fn=boom, initial_state={})


def test_ai_kit_step_fn_partial_state_checkpoint_resume(tmp_path: Path):
    from ai_kit.pipeline import AgentLoop

    cp_db = tmp_path / "cp.sqlite"
    trace = AppendOnlyLedger(tmp_path / "trace.sqlite")
    loop = AgentLoop(agent_id="p3-resume", checkpoint_db=cp_db, trace_ledger=trace)

    def step_fn(step: int, state: dict) -> dict:
        state["seen"] = state.get("seen", []) + [step]
        return state

    out = loop.run_steps(start_step=0, steps=2, step_fn=step_fn, initial_state={})
    assert out["seen"] == [0, 1]
    loop2 = AgentLoop(agent_id="p3-resume", checkpoint_db=cp_db, trace_ledger=trace)
    out2 = loop2.run_steps(start_step=0, steps=2, step_fn=step_fn, initial_state={})
    assert out2["seen"] == [0, 1, 2, 3]


def test_export_bundle_includes_epoch_roots(tmp_path: Path):
    db = tmp_path / "epoch.sqlite"
    ledger = AppendOnlyLedger(db)
    ledger.append(event_type="decision", payload={"x": 1}, manifest_id="e1")
    tar = tmp_path / "bundle.tar"
    result = build_audit_bundle(db, tarball_path=tar, product="phase3-epoch")
    assert result.ok
    with tarfile.open(tar, "r") as tf:
        epoch = json.loads(tf.extractfile("epoch_roots.json").read().decode())
    assert epoch["entry_count"] >= 1
    assert len(epoch["merkle_root"]) == 64
    assert verify_audit_bundle(tar).ok is True


@pytest.mark.parametrize(
    "body,expect_reject",
    [
        ({"campaignId": "x" * 500, "bidMicros": 1}, False),
        ({"unicode": "💸" * 50, "bidMicros": 1000}, False),
        ({"nested": {"html": "<script>alert(1)</script>"}, "bidMicros": 1000}, False),
    ],
)
@pytest.mark.asyncio
async def test_ad_guard_malformed_body_evaluate_stable(tmp_path: Path, body, expect_reject):
    from ad_guard.proxy import AdGuardGateway, AdSpendRequest

    gw = AdGuardGateway(shadow_mode=True)
    req = AdSpendRequest(
        client_id="fuzz",
        method="POST",
        path="/v1/campaigns",
        body=body,
        provider="generic",
    )
    resp = await gw.evaluate(req)
    assert resp.decision.value in ("approve", "reject", "kill")


@pytest.mark.asyncio
async def test_redis_stream_consumer_crash_reclaim():
    from webhook_mesh.queue import DeliveryManifest, RedisStreamDeliveryQueue

    mock_redis = AsyncMock()
    mock_redis.xgroup_create = AsyncMock()
    fields = DeliveryManifest(
        manifest_id="crash-reclaim-1",
        payload=b'{"id":"e1"}',
        target_url="https://example.com/hook",
        lamport=3,
    ).to_stream_fields()
    mock_redis.xautoclaim = AsyncMock(return_value=("0-0", [("99-0", fields)], []))
    queue = RedisStreamDeliveryQueue(mock_redis, claim_idle_ms=1000)
    reclaimed = await queue._reclaim_stale()
    assert reclaimed == [("99-0", fields)]
    mock_redis.xautoclaim.assert_awaited_once()
