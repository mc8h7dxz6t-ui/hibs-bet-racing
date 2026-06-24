"""Tests for Webhook Replay — capture store and deterministic replay."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from inst_spine.ledger import AppendOnlyLedger
from webhook_replay.capture import CaptureManifest, CaptureStore
from webhook_replay.replay_engine import ReplayEngine


def test_capture_roundtrip(tmp_path: Path):
    store = CaptureStore(tmp_path / "caps")
    body = b'{"id":"evt-1","amount":42}'
    manifest = CaptureManifest(
        capture_id="evt-1",
        tenant_id="t1",
        provider="stripe",
        headers={"X-Webhook-Id": "evt-1"},
        received_at_utc="2026-06-17T00:00:00Z",
    )
    path = store.write(manifest, body)
    m2, b2 = store.read(path)
    assert m2.capture_id == "evt-1"
    assert b2 == body
    assert m2.extras.get("payload_sha256")


def test_replay_detects_tampered_body(tmp_path: Path):
    store = CaptureStore(tmp_path / "caps")
    body = b'{"id":"evt-1"}'
    manifest = CaptureManifest(
        capture_id="evt-1",
        tenant_id="t1",
        provider="generic",
        headers={},
        received_at_utc="2026-06-17T00:00:00Z",
    )
    path = store.write(manifest, body)
    manifest2, body2 = store.read(path)
    tampered = body2 + b"x"
    engine = ReplayEngine(store)
    result = engine.replay_capture(manifest2, tampered)
    assert not result.ok
    assert any(d.field == "payload_sha256" for d in result.diffs)


def test_replay_logs_to_ledger(tmp_path: Path):
    store = CaptureStore(tmp_path / "caps")
    db = tmp_path / "ledger.sqlite"
    body = b'{"ok":true}'
    manifest = CaptureManifest(
        capture_id="evt-2",
        tenant_id="t1",
        provider="generic",
        headers={},
        received_at_utc="2026-06-17T00:00:00Z",
    )
    store.write(manifest, body)
    ledger = AppendOnlyLedger(db)
    engine = ReplayEngine(store, ledger=ledger)
    result = engine.replay_file(store.list_captures()[0])
    assert result.ok
    entries = ledger.list_entries()
    assert any(e["event_type"] == "webhook_replay" for e in entries)


def test_capture_mmap_readable(tmp_path: Path):
    store = CaptureStore(tmp_path / "caps")
    body = json.dumps({"large": "x" * 1000}).encode()
    manifest = CaptureManifest(
        capture_id="big-1",
        tenant_id="t1",
        provider="generic",
        headers={},
        received_at_utc="2026-06-17T00:00:00Z",
    )
    path = store.write(manifest, body)
    _, read_body = store.read(path)
    assert len(read_body) == len(body)
