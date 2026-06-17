"""Webhook mesh — idempotency CAS, HMAC, FSM, ingress."""

from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from inst_spine.rates import MemoryIdempotencyBackend, RedisIdempotencyBackend
from inst_spine.wal import WALWriter
from webhook_mesh.fsm import (
    SUCCESS_STATUS_CODES,
    dispatch_webhook_delivery,
    handle_dead_letter_allocation,
)
from webhook_mesh.hmac_verify import verify_provider_signature


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


def test_wal_writer_fsync_append(tmp_path: Path):
    wal = WALWriter(tmp_path / "mesh.wal")
    wal.append(payload={"manifest_id": "m1", "status": "RECEIVED"}, lamport=1, raw_bytes=b"{}")
    lines = (tmp_path / "mesh.wal").read_text(encoding="utf-8").strip().splitlines()
    record = json.loads(lines[0])
    assert record["manifest_id"] == "m1"
    assert record["payload_sha256"] == hashlib.sha256(b"{}").hexdigest()


@pytest.mark.asyncio
async def test_dispatch_delivery_success():
    response = MagicMock()
    response.status_code = 200
    client = AsyncMock()
    client.post = AsyncMock(return_value=response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)

    with patch("webhook_mesh.fsm.httpx.AsyncClient", return_value=client):
        ok = await dispatch_webhook_delivery("m1", b"{}", "https://example.com/hook", 3)
    assert ok is True


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
            )
    assert ok is False
    assert (tmp_path / "dlq" / "m-dead.bin").read_bytes() == b'{"x":1}'


@pytest.mark.asyncio
async def test_handle_dead_letter_writes_files(tmp_path: Path):
    path = await handle_dead_letter_allocation(
        "abc",
        b"payload",
        "https://target",
        dead_letter_dir=tmp_path,
    )
    assert path is not None
    assert path.read_bytes() == b"payload"


def test_success_status_codes_include_204():
    assert 204 in SUCCESS_STATUS_CODES


@pytest.mark.asyncio
async def test_ingress_accepts_and_dedupes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    secret = "ingress-secret"
    monkeypatch.setenv("WEBHOOK_PROVIDER_SECRET", secret)
    monkeypatch.setenv("INST_WAL_PATH", str(tmp_path / "ingress.wal"))

    import webhook_mesh.serve as serve_mod

    serve_mod.state = serve_mod.RuntimeState()
    serve_mod.state.provider_secret = secret
    serve_mod.state.wal_writer = WALWriter(tmp_path / "ingress.wal")
    serve_mod.state.idempotency_db = MemoryIdempotencyBackend()
    serve_mod.state.dead_letter_dir = str(tmp_path / "dlq")

    body = b'{"id":"evt-1"}'
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    headers = {
        "X-Provider-Signature": sig,
        "X-Webhook-Id": "evt-1",
        "X-Target-Forward-Url": "https://example.com/forward",
    }

    delivered: list[str] = []

    async def _fake_dispatch(**kwargs):
        delivered.append(kwargs["manifest_id"])

    with patch("webhook_mesh.serve.dispatch_webhook_delivery", side_effect=_fake_dispatch):
        client = TestClient(serve_mod.app)
        r1 = client.post("/v1/ingress/tenant-a", content=body, headers=headers)
        r2 = client.post("/v1/ingress/tenant-a", content=body, headers=headers)

    assert r1.status_code == 200
    assert r1.json()["status"] == "ACCEPTED"
    assert "manifest_id" in r1.json()
    assert r2.status_code == 200
    assert r2.json()["status"] == "ALREADY_PROCESSED"
    assert len(delivered) == 1
