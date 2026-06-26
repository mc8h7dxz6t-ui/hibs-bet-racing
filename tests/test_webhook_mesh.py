"""Webhook mesh — idempotency CAS, HMAC, FSM, ingress."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from inst_spine.rates import MemoryIdempotencyBackend, RedisIdempotencyBackend
from inst_spine.wal import WALWriter
from webhook_mesh.fsm import (
    DELIVERY_LIMITS,
    DELIVERY_TIMEOUT,
    SUCCESS_STATUS_CODES,
    dispatch_webhook_delivery,
    handle_dead_letter_allocation,
)
from webhook_mesh.hmac_verify import (
    verify_provider_signature,
    verify_shopify_hmac,
    verify_stripe_signature,
)
from webhook_mesh.queue import (
    BackgroundDeliveryQueue,
    CONSUMER_GROUP,
    DeliveryManifest,
    RedisStreamDeliveryQueue,
    STREAM_KEY,
    dispatch_mode_from_env,
)
from webhook_mesh.replay import assess_payload_integrity, can_replay_dead_letter, load_dead_letter_meta


@pytest.mark.asyncio
async def test_memory_idempotency_unique_then_duplicate():
    backend = MemoryIdempotencyBackend()
    assert await backend.consume_idempotency_token("k1", 60) is True
    assert await backend.consume_idempotency_token("k1", 60) is False


@pytest.mark.asyncio
async def test_memory_idempotency_expires():
    backend = MemoryIdempotencyBackend()
    assert await backend.consume_idempotency_token("k1", 1) is True
    backend._storage["k1"] = 0.0
    assert await backend.consume_idempotency_token("k1", 60) is True


@pytest.mark.asyncio
async def test_redis_idempotency_cas_success():
    script = AsyncMock(return_value=1)
    redis_client = MagicMock()
    redis_client.register_script.return_value = script
    backend = RedisIdempotencyBackend(redis_client)
    assert await backend.consume_idempotency_token("client:evt", 3600) is True
    script.assert_awaited_once()


@pytest.mark.asyncio
async def test_redis_idempotency_fail_closed_on_error():
    script = AsyncMock(side_effect=ConnectionError("redis down"))
    redis_client = MagicMock()
    redis_client.register_script.return_value = script
    backend = RedisIdempotencyBackend(redis_client)
    assert await backend.consume_idempotency_token("client:evt", 3600) is False


def test_hmac_verify_roundtrip():
    secret = "whsec_test"
    body = b'{"event":"payment"}'
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert verify_provider_signature(body, sig, secret)
    assert not verify_provider_signature(body, "bad", secret)
    assert not verify_provider_signature(body, sig, "")


def test_shopify_hmac_roundtrip():
    secret = "shopify-secret"
    body = b'{"id":1}'
    import base64

    digest = hmac.new(secret.encode(), body, hashlib.sha256).digest()
    sig = base64.b64encode(digest).decode("ascii")
    assert verify_shopify_hmac(body, sig, secret)
    assert not verify_shopify_hmac(body, "bad", secret)


def test_stripe_signature_roundtrip():
    import time

    secret = "whsec_test"
    body = b'{"id":"evt_123"}'
    ts = int(time.time())
    signed = f"{ts}.".encode("utf-8") + body
    v1 = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    header = f"t={ts},v1={v1}"
    assert verify_stripe_signature(body, header, secret)
    assert not verify_stripe_signature(body, header, "wrong")


def test_wal_writer_fsync_append(tmp_path: Path):
    wal = WALWriter(tmp_path / "mesh.wal")
    wal.append(payload={"manifest_id": "m1", "status": "RECEIVED"}, lamport=1, raw_bytes=b"{}")
    lines = (tmp_path / "mesh.wal").read_text(encoding="utf-8").strip().splitlines()
    record = json.loads(lines[0])
    assert record["manifest_id"] == "m1"
    assert record["payload_sha256"] == hashlib.sha256(b"{}").hexdigest()


def test_dispatch_uses_tiered_httpx_limits():
    assert DELIVERY_LIMITS.max_connections == 200
    assert DELIVERY_TIMEOUT.connect == 1.0


@pytest.mark.asyncio
async def test_dispatch_delivery_success():
    response = MagicMock()
    response.status_code = 200
    client = AsyncMock()
    client.post = AsyncMock(return_value=response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)

    with patch("webhook_mesh.fsm.httpx.AsyncClient", return_value=client) as client_ctor:
        ok = await dispatch_webhook_delivery("m1", b"{}", "https://example.com/hook", 3)
    assert ok is True
    assert client_ctor.call_args.kwargs["limits"] == DELIVERY_LIMITS


@pytest.mark.asyncio
async def test_dispatch_dead_letter_after_retries(tmp_path: Path):
    import httpx

    client = AsyncMock()
    client.post = AsyncMock(side_effect=httpx.RequestError("network"))
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)

    with patch("webhook_mesh.fsm.httpx.AsyncClient", return_value=client):
        with patch("webhook_mesh.fsm.asyncio.sleep", new_callable=AsyncMock):
            ok = await dispatch_webhook_delivery(
                "m-dead",
                b'{"x":1}',
                "https://example.com/hook",
                5,
                dead_letter_dir=tmp_path / "dlq",
                payload_id="evt-dead",
            )
    assert ok is False
    assert (tmp_path / "dlq" / "m-dead.bin").read_bytes() == b'{"x":1}'
    meta = load_dead_letter_meta(tmp_path / "dlq" / "evt-dead.err_unknown.json")
    assert meta["payload_id"] == "evt-dead"


@pytest.mark.asyncio
async def test_poison_json_blocks_replay(tmp_path: Path):
    await handle_dead_letter_allocation(
        "m-poison",
        b"not-json",
        "https://target",
        dead_letter_dir=tmp_path,
        payload_id="evt-poison",
        last_status_code=500,
    )
    meta = load_dead_letter_meta(tmp_path / "evt-poison.err_500.json")
    assert meta["replay_blocked"] is True
    allowed, _ = can_replay_dead_letter(meta)
    assert not allowed


@pytest.mark.asyncio
async def test_handle_dead_letter_writes_sidecar(tmp_path: Path):
    path = await handle_dead_letter_allocation(
        "abc",
        b'{"ok":true}',
        "https://target",
        dead_letter_dir=tmp_path,
        payload_id="evt-abc",
        last_status_code=500,
    )
    assert path is not None
    assert path.read_bytes() == b'{"ok":true}'
    meta = load_dead_letter_meta(tmp_path / "evt-abc.err_500.json")
    assert meta["manifest_id"] == "abc"


def test_assess_payload_integrity():
    ok, reason = assess_payload_integrity(b'{"a":1}')
    assert ok and reason is None
    ok, reason = assess_payload_integrity(b"{")
    assert not ok and reason.startswith("json_decode")


def test_success_status_codes_include_204():
    assert 204 in SUCCESS_STATUS_CODES


@pytest.mark.asyncio
async def test_ingress_accepts_and_dedupes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    secret = "ingress-secret"
    monkeypatch.setenv("WEBHOOK_PROVIDER_SECRET", secret)
    monkeypatch.setenv("INST_WAL_PATH", str(tmp_path / "ingress.wal"))

    monkeypatch.setenv("WEBHOOK_DISPATCH_MODE", "background")

    import webhook_mesh.serve as serve_mod

    captured: list[DeliveryManifest] = []

    class _CaptureQueue(BackgroundDeliveryQueue):
        async def enqueue(self, manifest: DeliveryManifest) -> None:
            captured.append(manifest)

    async def _test_startup() -> None:
        """Skip production startup — test injects RuntimeState directly."""
        return None

    monkeypatch.setattr(serve_mod, "initialize_spine_dependencies", _test_startup)

    serve_mod.state = serve_mod.RuntimeState()
    serve_mod.state.provider_secret = secret
    serve_mod.state.wal_writer = WALWriter(tmp_path / "ingress.wal")
    serve_mod.state.idempotency_db = MemoryIdempotencyBackend()
    serve_mod.state.dead_letter_dir = str(tmp_path / "dlq")
    serve_mod.state.delivery_queue = _CaptureQueue()
    serve_mod.state.dispatch_mode = "background"

    body = b'{"id":"evt-1"}'
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    headers = {
        "X-Provider-Signature": sig,
        "X-Webhook-Id": "evt-1",
        "X-Target-Forward-Url": "https://example.com/forward",
    }

    client = TestClient(serve_mod.app)
    try:
        r1 = client.post("/v1/ingress/tenant-a", content=body, headers=headers)
        r2 = client.post("/v1/ingress/tenant-a", content=body, headers=headers)

        assert r1.status_code == 200
        assert r1.json()["status"] == "ACCEPTED"
        assert r1.json()["dispatch_mode"] == "background"
        assert "manifest_id" in r1.json()
        assert r2.status_code == 200
        assert r2.json()["status"] == "ALREADY_PROCESSED"
        assert len(captured) == 1
    finally:
        client.close()


def test_delivery_manifest_stream_roundtrip():
    manifest = DeliveryManifest(
        manifest_id="m1",
        payload=b'{"id":1}',
        target_url="https://example.com/hook",
        lamport=7,
        client_id="t1",
        payload_id="p1",
    )
    fields = manifest.to_stream_fields()
    restored = DeliveryManifest.from_stream_fields(fields)
    assert restored.manifest_id == manifest.manifest_id
    assert restored.payload == manifest.payload
    assert restored.lamport == 7


def test_dispatch_mode_from_env_matrix(monkeypatch):
    monkeypatch.delenv("INST_REDIS_URL", raising=False)
    monkeypatch.setenv("WEBHOOK_DISPATCH_MODE", "background")
    assert dispatch_mode_from_env() == "background"
    monkeypatch.delenv("WEBHOOK_DISPATCH_MODE", raising=False)
    monkeypatch.setenv("INST_REDIS_URL", "redis://localhost:6379/0")
    assert dispatch_mode_from_env() == "redis"


@pytest.mark.asyncio
async def test_redis_stream_enqueue_xadd():
    redis_client = MagicMock()
    redis_client.xgroup_create = AsyncMock()
    redis_client.xadd = AsyncMock(return_value="1-0")
    queue = RedisStreamDeliveryQueue(redis_client)
    manifest = DeliveryManifest(
        manifest_id="m-redis",
        payload=b"{}",
        target_url="https://example.com",
        lamport=1,
    )
    await queue.enqueue(manifest)
    redis_client.xadd.assert_awaited_once()
    args, _ = redis_client.xadd.call_args
    assert args[0] == STREAM_KEY


@pytest.mark.asyncio
async def test_redis_stream_worker_acks_on_success(monkeypatch):
    redis_client = MagicMock()
    redis_client.xgroup_create = AsyncMock()
    redis_client.xautoclaim = AsyncMock(return_value=("0-0", [], []))
    redis_client.xreadgroup = AsyncMock(
        side_effect=[
            [
                (
                    STREAM_KEY,
                    [
                        (
                            "42-0",
                            DeliveryManifest(
                                manifest_id="m-ok",
                                payload=b"{}",
                                target_url="https://example.com",
                                lamport=2,
                            ).to_stream_fields(),
                        )
                    ],
                )
            ],
            asyncio.CancelledError(),
        ]
    )
    redis_client.xack = AsyncMock()
    queue = RedisStreamDeliveryQueue(redis_client)
    monkeypatch.setattr(
        "webhook_mesh.fsm.dispatch_webhook_delivery",
        AsyncMock(return_value=True),
    )
    queue._running = True
    with pytest.raises(asyncio.CancelledError):
        await queue._consume_loop()
    redis_client.xack.assert_awaited_with(STREAM_KEY, CONSUMER_GROUP, "42-0")


@pytest.mark.asyncio
async def test_redis_stream_worker_acks_after_dlq(monkeypatch):
    redis_client = MagicMock()
    redis_client.xgroup_create = AsyncMock()
    redis_client.xautoclaim = AsyncMock(return_value=("0-0", [], []))
    redis_client.xreadgroup = AsyncMock(
        side_effect=[
            [
                (
                    STREAM_KEY,
                    [
                        (
                            "99-0",
                            DeliveryManifest(
                                manifest_id="m-fail",
                                payload=b"{}",
                                target_url="https://example.com",
                                lamport=3,
                            ).to_stream_fields(),
                        )
                    ],
                )
            ],
            asyncio.CancelledError(),
        ]
    )
    redis_client.xack = AsyncMock()
    queue = RedisStreamDeliveryQueue(redis_client)
    monkeypatch.setattr(
        "webhook_mesh.fsm.dispatch_webhook_delivery",
        AsyncMock(return_value=False),
    )
    queue._running = True
    with pytest.raises(asyncio.CancelledError):
        await queue._consume_loop()
    redis_client.xack.assert_awaited_with(STREAM_KEY, CONSUMER_GROUP, "99-0")


@pytest.mark.asyncio
async def test_redis_stream_worker_no_ack_on_exception(monkeypatch):
    redis_client = MagicMock()
    redis_client.xgroup_create = AsyncMock()
    redis_client.xautoclaim = AsyncMock(return_value=("0-0", [], []))
    redis_client.xreadgroup = AsyncMock(
        side_effect=[
            [
                (
                    STREAM_KEY,
                    [
                        (
                            "77-0",
                            DeliveryManifest(
                                manifest_id="m-exc",
                                payload=b"{}",
                                target_url="https://example.com",
                                lamport=4,
                            ).to_stream_fields(),
                        )
                    ],
                )
            ],
            asyncio.CancelledError(),
        ]
    )
    redis_client.xack = AsyncMock()
    queue = RedisStreamDeliveryQueue(redis_client)
    monkeypatch.setattr(
        "webhook_mesh.fsm.dispatch_webhook_delivery",
        AsyncMock(side_effect=RuntimeError("boom")),
    )
    queue._running = True
    with pytest.raises(asyncio.CancelledError):
        await queue._consume_loop()
    redis_client.xack.assert_not_awaited()

