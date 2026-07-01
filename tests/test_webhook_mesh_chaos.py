"""Webhook mesh chaos — poison + stream lifecycle (Wave 3)."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from inst_spine.ledger import AppendOnlyLedger
from webhook_mesh.audit import append_delivery_event
from webhook_replay.capture import CaptureManifest, CaptureStore


def test_wrcap_header_corruption_fuzz(tmp_path: Path):
    cap_dir = tmp_path / "caps"
    store = CaptureStore(cap_dir)
    manifest = CaptureManifest(
        capture_id="fuzz-1",
        tenant_id="t1",
        provider="test",
        headers={"Content-Type": "application/json"},
        received_at_utc="2026-01-01T00:00:00Z",
        lamport_seq=1,
    )
    path = store.write(manifest, b'{"ok":true}')
    raw = path.read_bytes()
    path.write_bytes(raw[: max(1, len(raw) // 2)])
    with pytest.raises((ValueError, OSError, EOFError, json.JSONDecodeError)):
        store.read(path)


def test_webhook_poison_delivery_status_on_ledger(tmp_path: Path, monkeypatch):
    import json

    db = tmp_path / "mesh.sqlite"
    monkeypatch.setenv("WEBHOOK_MESH_LEDGER", str(db))
    append_delivery_event(
        manifest_id="poison-1",
        status="POISON",
        lamport=3,
        raw_bytes=b"not-json",
        extra={"detail": "max_retries_exceeded"},
    )
    entries = AppendOnlyLedger(db).list_entries()
    statuses = [
        (e.get("payload") or {}).get("status")
        for e in entries
        if e.get("event_type") == "webhook_delivery"
    ]
    assert statuses == ["POISON"]


@pytest.mark.asyncio
async def test_redis_stream_enqueue_fields_roundtrip():
    from webhook_mesh.queue import DeliveryManifest

    m = DeliveryManifest(
        manifest_id="m-stream-1",
        payload=b'{"event":"test"}',
        target_url="https://example.com/hook",
        lamport=7,
        client_id="c1",
    )
    fields = m.to_stream_fields()
    restored = DeliveryManifest.from_stream_fields(fields)
    assert restored.manifest_id == m.manifest_id
    assert restored.payload == m.payload
    assert base64.b64encode(restored.payload).decode() == fields["payload_b64"]


@pytest.mark.asyncio
async def test_stream_worker_enqueue_calls_xadd():
    from webhook_mesh.queue import DeliveryManifest, RedisStreamDeliveryQueue

    manifest = DeliveryManifest(
        manifest_id="crash-1",
        payload=b"{}",
        target_url="https://httpbin.org/post",
        lamport=1,
    )
    mock_redis = AsyncMock()
    mock_redis.xgroup_create = AsyncMock()
    mock_redis.xadd = AsyncMock(return_value=b"1-0")
    queue = RedisStreamDeliveryQueue(mock_redis)
    await queue.enqueue(manifest)
    mock_redis.xadd.assert_awaited_once()
