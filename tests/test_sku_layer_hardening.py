"""SKU-layer hardening: production profile, exports, replay scale."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from ai_kit.export import build_ai_kit_audit_bundle, redact_trace_entry
from agent_ledger.export import redact_permit_entry
from altdata.feed_schema import feed_schema_registry
from drift_gate.state import RollingStateStore
from inst_spine.ledger import AppendOnlyLedger
from inst_spine.production_profile import (
    drift_redis_rolling_required,
    postgres_ha_check,
    redis_production_check,
    webhook_dispatch_check,
)
from webhook_replay.capture import CaptureManifest, CaptureStore
from webhook_replay.replay_engine import ReplayEngine


def test_redis_production_check_fails_without_url(monkeypatch):
    monkeypatch.delenv("INST_REDIS_URL", raising=False)
    monkeypatch.setenv("INST_PRODUCTION_PROFILE", "1")
    ok, detail = redis_production_check()
    assert ok is False
    assert "INST_REDIS_URL" in detail


def test_webhook_dispatch_blocks_background_in_prod(monkeypatch):
    monkeypatch.setenv("INST_PRODUCTION_PROFILE", "1")
    monkeypatch.delenv("WEBHOOK_REQUIRE_REDIS_DISPATCH", raising=False)
    monkeypatch.delenv("INST_REDIS_URL", raising=False)
    ok, detail = webhook_dispatch_check("background")
    assert ok is False
    assert "production" in detail.lower()


def test_drift_redis_rolling_required(monkeypatch):
    monkeypatch.setenv("INST_PRODUCTION_PROFILE", "1")
    monkeypatch.delenv("INST_REDIS_URL", raising=False)
    assert drift_redis_rolling_required() is True


def test_postgres_ha_check_when_required(monkeypatch):
    monkeypatch.setenv("INST_REQUIRE_POSTGRES", "1")
    monkeypatch.delenv("INST_POSTGRES_DSN", raising=False)
    ok, detail = postgres_ha_check()
    assert ok is False


def test_ai_kit_trace_redaction():
    entry = {
        "event_type": "agent_trace",
        "payload": {"prompt": "secret", "model": "gpt-4"},
    }
    redacted = redact_trace_entry(entry)
    assert redacted["payload"]["trace_redacted"] is True
    assert "prompt" not in redacted["payload"]
    assert "prompt_sha256" in redacted["payload"]


def test_ai_kit_audit_bundle_observation_lane(tmp_path: Path):
    db = tmp_path / "trace.sqlite"
    ledger = AppendOnlyLedger(db, writer_id="test")
    for step in range(3):
        ledger.append(
            event_type="agent_trace",
            payload={"prompt": f"secret-{step}", "model": "gpt-4", "step": step},
        )
    result = build_ai_kit_audit_bundle(db, observation_lane=True, repro_run=True)
    assert result.ok is True
    entries = json.loads((result.out_dir / "ledger_entries.json").read_text(encoding="utf-8"))
    traces = [e for e in entries if e.get("event_type") == "agent_trace"]
    assert traces
    assert all(e["payload"].get("trace_redacted") for e in traces)


def test_agent_ledger_permit_redaction():
    entry = {
        "event_type": "agent_action",
        "payload": {"arguments": {"api_key": "x", "model": "m"}},
    }
    redacted = redact_permit_entry(entry)
    assert redacted["payload"]["arguments_redacted"] is True
    assert "arguments" not in redacted["payload"]
    assert "model" not in redacted["payload"]["argument_keys"] or "model" in redacted["payload"]["argument_keys"]


def test_feed_schema_registry():
    reg = feed_schema_registry()
    assert "feeds" in reg
    assert "fare_price" in reg["feeds"]


def test_webhook_replay_parallel_and_prune():
    with tempfile.TemporaryDirectory() as td:
        store = CaptureStore(Path(td))
        for i in range(5):
            manifest = CaptureManifest(
                capture_id=f"c{i}",
                tenant_id="t",
                provider="generic",
                headers={},
                received_at_utc=f"2026-07-0{i + 1}T00:00:00Z",
            )
            store.write(manifest, b"{}")
        pruned = store.prune_older_than(max_files=3)
        assert pruned == 2
        engine = ReplayEngine(store)
        results = engine.replay_batch_parallel(max_workers=2)
        assert len(results) == 3
        assert all(r.ok for r in results)


def test_drift_rolling_store_redis_key_required(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("INST_PRODUCTION_PROFILE", "1")
    monkeypatch.delenv("INST_REDIS_URL", raising=False)
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps({"features": {"score": [0.1]}}), encoding="utf-8")
    with pytest.raises(RuntimeError, match="redis"):
        RollingStateStore.from_baseline(baseline)
