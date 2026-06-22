"""Proxy-Risk gateway — live forward, idempotency, latency."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from inst_spine.gates.circuit import CircuitBreaker, CircuitState
from inst_spine.ledger import AppendOnlyLedger
from inst_spine.rates import MemoryIdempotencyBackend, MemoryTokenBucketBackend, TokenBucket
from proxy_risk.router import GateDecision, ProxyRequest, ProxyRiskGateway


@pytest.mark.asyncio
async def test_proxy_risk_idempotency_duplicate():
    gw = ProxyRiskGateway(
        shadow_mode=True,
        idempotency=MemoryIdempotencyBackend(),
    )
    req = ProxyRequest(
        client_id="c1",
        method="POST",
        path="/orders",
        body={"qty": 1},
        idempotency_key="dup-key-1",
    )
    r1 = await gw.evaluate(req)
    r2 = await gw.evaluate(req)
    assert r1.decision == GateDecision.APPROVE
    assert r2.decision == GateDecision.REJECT
    assert "idempotency" in r2.reason


@pytest.mark.asyncio
async def test_proxy_risk_circuit_kill_env():
    circuit = CircuitBreaker(state=CircuitState.KILL, reason="test kill")
    gw = ProxyRiskGateway(circuit=circuit, shadow_mode=True)
    resp = await gw.evaluate(ProxyRequest(client_id="c", method="POST", path="/x", body={}))
    assert resp.decision == GateDecision.KILL


@pytest.mark.asyncio
async def test_proxy_risk_logs_reject_and_kill(tmp_path: Path):
    db = tmp_path / "audit.sqlite"
    ledger = AppendOnlyLedger(db, async_writes=True)
    ledger.start_async_writer()
    gw = ProxyRiskGateway(
        ledger=ledger,
        shadow_mode=True,
        idempotency=MemoryIdempotencyBackend(),
    )
    await gw.evaluate(
        ProxyRequest(
            client_id="c1",
            method="POST",
            path="/dup",
            body={},
            idempotency_key="same-key",
        )
    )
    await gw.evaluate(
        ProxyRequest(
            client_id="c1",
            method="POST",
            path="/dup",
            body={},
            idempotency_key="same-key",
        )
    )
    ledger.stop_async_writer(flush=True)
    rows = [e for e in ledger.list_entries() if e.get("event_type") == "proxy_request"]
    decisions = [r.get("payload", {}).get("decision") for r in rows]
    assert "approve" in decisions
    assert "reject" in decisions


@pytest.mark.asyncio
async def test_proxy_risk_upstream_failure_rejects():
    mock_resp = MagicMock()
    mock_resp.status_code = 503
    mock_resp.json.return_value = {"error": "unavailable"}
    mock_resp.text = '{"error":"unavailable"}'
    mock_client = AsyncMock()
    mock_client.request = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    gw = ProxyRiskGateway(
        shadow_mode=False,
        upstream_base="https://api.example.com",
        idempotency=MemoryIdempotencyBackend(),
    )
    with patch("proxy_risk.router.httpx.AsyncClient", return_value=mock_client):
        resp = await gw.evaluate(
            ProxyRequest(
                client_id="c",
                method="POST",
                path="/orders",
                idempotency_key="fail-1",
            )
        )
    assert resp.decision == GateDecision.REJECT
    assert resp.upstream_status == 503


@pytest.mark.asyncio
async def test_redis_token_bucket_fail_closed():
    from inst_spine.rates import RedisTokenBucketBackend

    backend = object.__new__(RedisTokenBucketBackend)
    backend._script = MagicMock(side_effect=RuntimeError("redis down"))
    backend._prefix = "t:"
    assert backend.consume(key="k", capacity=10.0, refill_rate=1.0, cost=1.0, now=1.0) is False


@pytest.mark.asyncio
async def test_proxy_risk_ledger_chain(tmp_path: Path):
    db = tmp_path / "proxy.sqlite"
    ledger = AppendOnlyLedger(db, async_writes=True)
    ledger.start_async_writer()
    gw = ProxyRiskGateway(ledger=ledger, shadow_mode=True, idempotency=MemoryIdempotencyBackend())
    await gw.evaluate(ProxyRequest(client_id="c1", method="POST", path="/a", body={"n": 1}))
    await gw.evaluate(ProxyRequest(client_id="c1", method="POST", path="/b", body={"n": 2}))
    ledger.stop_async_writer(flush=True)
    verify = ledger.verify()
    assert verify["chain_ok"]
    assert verify["lamport_monotonic"]


@pytest.mark.asyncio
async def test_proxy_risk_live_upstream_forward():
    mock_resp = MagicMock()
    mock_resp.status_code = 201
    mock_resp.json.return_value = {"order_id": "ord_123"}
    mock_resp.text = '{"order_id": "ord_123"}'

    mock_client = AsyncMock()
    mock_client.request = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    gw = ProxyRiskGateway(
        shadow_mode=False,
        upstream_base="https://api.example.com",
        idempotency=MemoryIdempotencyBackend(),
    )
    gw.vault.set_secret("upstream", "tok_demo")

    with patch("proxy_risk.router.httpx.AsyncClient", return_value=mock_client):
        resp = await gw.evaluate(
            ProxyRequest(
                client_id="broker-1",
                method="POST",
                path="/v1/orders",
                body={"symbol": "AAPL", "qty": 10},
                idempotency_key="live-1",
            )
        )

    assert resp.decision == GateDecision.APPROVE
    assert resp.upstream_status == 201
    assert resp.upstream_body == {"order_id": "ord_123"}
    mock_client.request.assert_awaited_once()
    call_kwargs = mock_client.request.await_args
    assert call_kwargs.args[0] == "POST"
    assert call_kwargs.args[1] == "https://api.example.com/v1/orders"
    assert call_kwargs.kwargs["headers"]["Authorization"] == "Bearer tok_demo"


@pytest.mark.asyncio
async def test_proxy_risk_live_log_before_forward(tmp_path: Path):
    db = tmp_path / "live.sqlite"
    ledger = AppendOnlyLedger(db)
    gw = ProxyRiskGateway(
        ledger=ledger,
        shadow_mode=False,
        upstream_base="https://api.example.com",
        idempotency=MemoryIdempotencyBackend(),
    )

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"ok": True}
    mock_resp.text = "{}"
    mock_client = AsyncMock()
    mock_client.request = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("proxy_risk.router.httpx.AsyncClient", return_value=mock_client):
        await gw.evaluate(
            ProxyRequest(
                client_id="c",
                method="GET",
                path="/health",
                idempotency_key="log-before-1",
            )
        )

    entries = ledger.list_entries()
    proxy_rows = [e for e in entries if e.get("event_type") == "proxy_request"]
    assert len(proxy_rows) >= 1
    assert any("forward pending" in str(e.get("payload", {}).get("detail", "")) for e in proxy_rows)


@pytest.mark.asyncio
async def test_proxy_risk_p99_shadow_latency():
    backend = MemoryTokenBucketBackend()
    bucket = TokenBucket(capacity=100_000.0, refill_rate=100_000.0, key="bench", backend=backend)
    gw = ProxyRiskGateway(
        shadow_mode=True,
        bucket=bucket,
        idempotency=MemoryIdempotencyBackend(),
    )
    latencies_ms: list[float] = []
    for i in range(10_000):
        t0 = time.perf_counter()
        await gw.evaluate(
            ProxyRequest(
                client_id="bench",
                method="POST",
                path=f"/orders/{i}",
                body={"i": i},
            )
        )
        latencies_ms.append((time.perf_counter() - t0) * 1000.0)

    latencies_ms.sort()
    p99 = latencies_ms[int(len(latencies_ms) * 0.99) - 1]
    assert p99 < 10.0, f"p99 {p99:.3f}ms exceeds 10ms shadow target"
