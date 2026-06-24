"""Industry gold — chaos, integration, and latency invariants."""

from __future__ import annotations

import json
import os
import time
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from drift_gate.baseline import FeatureBaseline
from drift_gate.gate import DriftGate, DriftGateConfig, DriftGateMode, DriftGateRequest
from drift_gate.state import RollingStateStore
from inst_spine.ledger import AppendOnlyLedger
from inst_spine.rates import MemoryIdempotencyBackend
from inst_spine.wal import AppendOnlyWal
from proxy_risk.router import GateDecision, ProxyRequest, ProxyRiskGateway
from spend_guard.wallet import SpendWallet
from webhook_replay.capture import CaptureManifest, CaptureStore
from webhook_replay.replay_engine import ReplayEngine


def test_wal_fsync_survives_reopen(tmp_path: Path):
    wal_path = tmp_path / "chaos.wal"
    wal = AppendOnlyWal(wal_path)
    wal.append({"entry_id": "e1", "event": "test"})
    wal2 = AppendOnlyWal(wal_path)
    records = wal2.read_all()
    assert len(records) == 1
    assert records[0]["entry_id"] == "e1"


def test_rolling_state_persists_across_instances(tmp_path: Path):
    baseline = tmp_path / "base.json"
    FeatureBaseline(model_id="m1", version="v1", features={"x": [1.0] * 40}).save(baseline)
    state_path = tmp_path / "rolling.json"
    s1 = RollingStateStore.from_baseline(baseline, state_path=state_path)
    gate = DriftGate(
        FeatureBaseline.load(baseline),
        config=DriftGateConfig(min_current_samples=1, min_baseline_samples=10),
        rolling_window=s1.as_dict(),
    )
    gate.evaluate(DriftGateRequest(model_id="m1", version="v1", feature_vector={"x": 2.0}))
    s1._data = gate._rolling
    s1.save()
    s2 = RollingStateStore.from_baseline(baseline, state_path=state_path)
    assert len(s2.as_dict().get("x", [])) >= 1


@pytest.mark.asyncio
async def test_proxy_drift_gate_integration_shadow(tmp_path: Path):
    baseline = tmp_path / "drift.json"
    bl = FeatureBaseline(model_id="credit", version="v1")
    bl.features["income"] = [50000.0 + i for i in range(50)]
    bl.save(baseline)
    db = tmp_path / "proxy.sqlite"
    ledger = AppendOnlyLedger(db, async_writes=True)
    ledger.start_async_writer()
    try:
        gw = ProxyRiskGateway(
            ledger=ledger,
            shadow_mode=True,
            idempotency=MemoryIdempotencyBackend(),
            drift_baseline_path=str(baseline),
            drift_mode="shadow",
        )
        for i, income in enumerate([50100.0] * 5):
            resp = await gw.evaluate(
                ProxyRequest(
                    client_id="c1",
                    method="POST",
                    path="/infer",
                    body={"features": {"income": income, "debt_ratio": 0.35}, "seq": i},
                    idempotency_key=f"burn-{i}",
                )
            )
            assert resp.decision == GateDecision.APPROVE
        resp = await gw.evaluate(
            ProxyRequest(
                client_id="c1",
                method="POST",
                path="/infer",
                body={"features": {"income": 500000.0, "debt_ratio": 0.99}, "seq": 99},
                idempotency_key="drift-spike",
            )
        )
        assert resp.decision == GateDecision.APPROVE
        entries = ledger.list_entries()
        assert any(e.get("event_type") == "drift_gate_evaluation" for e in entries)
    finally:
        ledger.close()


def test_webhook_mesh_capture_integration(tmp_path: Path):
    capture_dir = tmp_path / "caps"
    os.environ["WEBHOOK_REPLAY_CAPTURE_DIR"] = str(capture_dir)
    try:
        from fastapi.testclient import TestClient

        import webhook_mesh.serve as serve_mod
        from inst_spine.wal import WALWriter

        db = tmp_path / "wh.sqlite"
        wal = tmp_path / "ingress.wal"
        secret = "chaos-secret"
        os.environ["WEBHOOK_MESH_LEDGER"] = str(db)

        class _NoQueue:
            async def enqueue(self, manifest):  # noqa: ANN001
                return None

        serve_mod.state = serve_mod.RuntimeState()
        serve_mod.state.provider_secret = secret
        serve_mod.state.wal_writer = WALWriter(wal)
        serve_mod.state.idempotency_db = MemoryIdempotencyBackend()
        serve_mod.state.dead_letter_dir = str(tmp_path / "dlq")
        serve_mod.state.delivery_queue = _NoQueue()
        serve_mod.state.dispatch_mode = "background"

        import hashlib
        import hmac

        body = b'{"id":"cap-1"}'
        sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        client = TestClient(serve_mod.app)
        r = client.post(
            "/v1/ingress/tenant-chaos",
            content=body,
            headers={
                "X-Provider-Signature": sig,
                "X-Webhook-Id": "cap-1",
                "X-Target-Forward-Url": "https://example.com/hook",
            },
        )
        assert r.status_code == 200
        caps = list(capture_dir.glob("*.wrcap"))
        assert len(caps) == 1
    finally:
        os.environ.pop("WEBHOOK_REPLAY_CAPTURE_DIR", None)


def test_spend_wallet_fail_closed_on_duplicate(tmp_path: Path):
    wallet = SpendWallet(tmp_path / "w.sqlite", initial_balance=100.0)
    ok1, _, h1 = wallet.reserve(10.0, request_id="same-id")
    ok2, reason2, _ = wallet.reserve(10.0, request_id="same-id")
    assert ok1 and not ok2
    assert "duplicate" in reason2


def test_replay_tamper_fails_closed(tmp_path: Path):
    store = CaptureStore(tmp_path / "caps")
    body = b'{"id":"t1"}'
    manifest = CaptureManifest(
        capture_id="t1",
        tenant_id="t",
        provider="generic",
        headers={},
        received_at_utc="2026-06-24T00:00:00Z",
    )
    path = store.write(manifest, body)
    m, b = store.read(path)
    engine = ReplayEngine(store)
    result = engine.replay_capture(m, b + b"tampered")
    assert not result.ok


@pytest.mark.asyncio
async def test_redis_stream_delivery_integration(monkeypatch, tmp_path: Path):
    """Redis Stream enqueue → worker dispatch → ACK (mocked redis)."""
    from unittest.mock import AsyncMock, MagicMock

    from webhook_mesh.queue import (
        CONSUMER_GROUP,
        DeliveryManifest,
        RedisStreamDeliveryQueue,
        STREAM_KEY,
    )

    redis_client = MagicMock()
    redis_client.xgroup_create = AsyncMock()
    redis_client.xautoclaim = AsyncMock(return_value=("0-0", [], []))
    manifest = DeliveryManifest(
        manifest_id="chaos-stream-1",
        payload=b'{"id":"stream-1"}',
        target_url="https://example.com/hook",
        lamport=9,
        payload_id="stream-1",
    )
    redis_client.xadd = AsyncMock(return_value="100-0")
    redis_client.xreadgroup = AsyncMock(
        side_effect=[
            [(STREAM_KEY, [("100-0", manifest.to_stream_fields())])],
            asyncio.CancelledError(),
        ]
    )
    redis_client.xack = AsyncMock()
    queue = RedisStreamDeliveryQueue(redis_client)
    await queue.enqueue(manifest)
    redis_client.xadd.assert_awaited_once()

    delivered = {"ok": False}

    async def _fake_dispatch(**kwargs):  # noqa: ANN003
        delivered["ok"] = True
        return True

    monkeypatch.setattr("webhook_mesh.fsm.dispatch_webhook_delivery", _fake_dispatch)
    queue._running = True
    with pytest.raises(asyncio.CancelledError):
        await queue._consume_loop()
    assert delivered["ok"] is True
    redis_client.xack.assert_awaited_with(STREAM_KEY, CONSUMER_GROUP, "100-0")


@pytest.mark.asyncio
async def test_redis_stream_with_capture_integration(tmp_path: Path):
    """Ingress + Redis stream mode + replay capture (industry gold)."""
    capture_dir = tmp_path / "caps"
    os.environ["WEBHOOK_REPLAY_CAPTURE_DIR"] = str(capture_dir)
    os.environ["WEBHOOK_DISPATCH_MODE"] = "redis"
    try:
        from unittest.mock import AsyncMock, MagicMock

        from fastapi.testclient import TestClient

        import webhook_mesh.serve as serve_mod
        from inst_spine.wal import WALWriter
        from webhook_mesh.queue import RedisStreamDeliveryQueue

        db = tmp_path / "wh.sqlite"
        wal = tmp_path / "ingress.wal"
        secret = "stream-capture-secret"
        os.environ["WEBHOOK_MESH_LEDGER"] = str(db)

        redis_client = MagicMock()
        redis_client.xgroup_create = AsyncMock()
        redis_client.xadd = AsyncMock(return_value="1-0")

        class _StreamQueue(RedisStreamDeliveryQueue):
            async def start_worker(self, handler=None):  # noqa: ANN001
                return None

        serve_mod.state = serve_mod.RuntimeState()
        serve_mod.state.provider_secret = secret
        serve_mod.state.wal_writer = WALWriter(wal)
        serve_mod.state.idempotency_db = MemoryIdempotencyBackend()
        serve_mod.state.dead_letter_dir = str(tmp_path / "dlq")
        serve_mod.state.delivery_queue = _StreamQueue(redis_client)
        serve_mod.state.dispatch_mode = "redis"

        import hashlib
        import hmac

        body = b'{"id":"stream-cap-1"}'
        sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        client = TestClient(serve_mod.app)
        r = client.post(
            "/v1/ingress/tenant-stream",
            content=body,
            headers={
                "X-Provider-Signature": sig,
                "X-Webhook-Id": "stream-cap-1",
                "X-Target-Forward-Url": "https://example.com/hook",
            },
        )
        assert r.status_code == 200
        assert r.json()["dispatch_mode"] == "redis"
        redis_client.xadd.assert_awaited_once()
        caps = list(capture_dir.glob("*.wrcap"))
        assert len(caps) == 1
    finally:
        os.environ.pop("WEBHOOK_REPLAY_CAPTURE_DIR", None)
        os.environ.pop("WEBHOOK_DISPATCH_MODE", None)


@pytest.mark.asyncio
async def test_spend_guard_http_reserve_settle_path(tmp_path: Path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    import spend_guard.serve as serve_mod

    wallet_db = tmp_path / "wallet.sqlite"
    ledger_db = tmp_path / "ledger.sqlite"
    from spend_guard.wallet import SpendWallet

    SpendWallet(wallet_db, initial_balance=200.0)
    serve_mod.state.wallet_db = str(wallet_db)
    serve_mod.state.ledger_db = str(ledger_db)
    serve_mod.state.mock_upstream = True
    serve_mod.state.gateway = None

    with TestClient(serve_mod.app) as client:
        r = client.post(
            "/v1/chat/completions",
            json={
                "model": "demo-model",
                "messages": [{"role": "user", "content": "rigorous"}],
                "max_tokens": 16,
            },
            headers={"X-Request-Id": "industry-gold-http-1"},
        )
        assert r.status_code == 200
        if serve_mod.state.ledger:
            serve_mod.state.ledger.stop_async_writer(flush=True)
        ledger = AppendOnlyLedger(ledger_db)
        phases = [e["payload"].get("phase") for e in ledger.list_entries() if e.get("event_type") == "spend_guard"]
        assert "reserve" in phases and "settle" in phases


@pytest.mark.asyncio
async def test_proxy_shadow_latency_p99_under_10ms():
    gw = ProxyRiskGateway(shadow_mode=True, idempotency=MemoryIdempotencyBackend())
    req = ProxyRequest(client_id="bench", method="POST", path="/x", body={"n": 1})
    latencies: list[float] = []
    for _ in range(2000):
        t0 = time.perf_counter()
        await gw.evaluate(req)
        latencies.append((time.perf_counter() - t0) * 1000.0)
    latencies.sort()
    p99 = latencies[int(len(latencies) * 0.99) - 1]
    assert p99 < 10.0, f"p99 {p99:.3f}ms exceeds 10ms industry gold target"
