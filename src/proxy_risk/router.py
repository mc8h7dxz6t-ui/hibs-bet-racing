"""Async proxy gateway — hot path memory only, cold path ledger."""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import httpx

from inst_spine.gates.circuit import CircuitBreaker, CredentialVault
from inst_spine.ledger import AppendOnlyLedger
from inst_spine.rates import (
    IdempotencyBackend,
    TokenBucket,
    ZScoreDriftDetector,
    idempotency_backend_from_env,
    token_bucket_backend_from_env,
)

_UPSTREAM_LIMITS = httpx.Limits(max_keepalive_connections=20, max_connections=100)
_UPSTREAM_TIMEOUT = httpx.Timeout(5.0, connect=2.0)


class GateDecision(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"
    KILL = "kill"


@dataclass
class ProxyRequest:
    client_id: str
    method: str
    path: str
    body: dict[str, Any] = field(default_factory=dict)
    idempotency_key: str | None = None
    reference_price: float | None = None


@dataclass
class ProxyResponse:
    decision: GateDecision
    reason: str
    upstream_status: int | None = None
    upstream_body: dict[str, Any] | None = None


class ProxyRiskGateway:
    """
    Hot-path gate chain (<5ms target in-memory):
      circuit → schema → token bucket → idempotency → z-score drift → forward
    Cold path: async ledger append (shadow) or sync WAL before forward (live).
    """

    def __init__(
        self,
        *,
        ledger: AppendOnlyLedger | None = None,
        bucket: TokenBucket | None = None,
        bucket_capacity: float = 30.0,
        bucket_refill: float = 5.0,
        drift: ZScoreDriftDetector | None = None,
        circuit: CircuitBreaker | None = None,
        vault: CredentialVault | None = None,
        shadow_mode: bool = True,
        rate_backend: Any | None = None,
        idempotency: IdempotencyBackend | None = None,
        upstream_base: str | None = None,
        idempotency_ttl_sec: int = 300,
    ) -> None:
        self.ledger = ledger
        self._rate_backend = rate_backend or token_bucket_backend_from_env()
        self._bucket_capacity = bucket_capacity
        self._bucket_refill = bucket_refill
        self.bucket = bucket
        self.drift = drift or ZScoreDriftDetector()
        self.circuit = circuit or CircuitBreaker.from_env()
        self.vault = vault or CredentialVault()
        token = os.environ.get("PROXY_RISK_UPSTREAM_TOKEN", "").strip()
        if token:
            self.vault.set_secret("upstream", token)
        self.shadow_mode = shadow_mode
        self.idempotency = idempotency or idempotency_backend_from_env()
        self.upstream_base = (upstream_base or os.environ.get("PROXY_RISK_UPSTREAM_BASE", "")).strip()
        self.idempotency_ttl_sec = idempotency_ttl_sec
        self._required_fields = ("client_id", "method", "path")

    async def evaluate(self, req: ProxyRequest) -> ProxyResponse:
        """Hot-path gate evaluation — no disk I/O except live log-before-forward."""
        allowed, reason = self.circuit.allows_traffic()
        if not allowed:
            return ProxyResponse(decision=GateDecision.KILL, reason=reason)

        if not req.client_id or not req.method or not req.path:
            return ProxyResponse(decision=GateDecision.REJECT, reason="schema: missing required fields")

        bucket = self.bucket or TokenBucket(
            capacity=self._bucket_capacity,
            refill_rate=self._bucket_refill,
            key=f"proxy:{req.client_id}",
            backend=self._rate_backend,
        )
        if not bucket.consume(1.0):
            return ProxyResponse(decision=GateDecision.REJECT, reason="token_bucket: rate exceeded")

        idem_key = req.idempotency_key or (
            f"{req.client_id}:{req.method}:{req.path}:{json.dumps(req.body, sort_keys=True)}"
        )
        if not await self.idempotency.consume_idempotency_token(idem_key, self.idempotency_ttl_sec):
            return ProxyResponse(decision=GateDecision.REJECT, reason="idempotency: duplicate request")

        if req.reference_price is not None:
            anomaly, z = self.drift.is_anomaly(req.reference_price)
            if anomaly:
                self.circuit.kill(f"z_score drift |Z|>{self.drift.z_max} (z={z:.2f})")
                await self._log_async(req, GateDecision.KILL, f"drift: z={z:.2f}")
                return ProxyResponse(decision=GateDecision.KILL, reason=f"drift: z={z:.2f}")

        if self.shadow_mode:
            await self._log_async(req, GateDecision.APPROVE, "shadow forward")
            return ProxyResponse(decision=GateDecision.APPROVE, reason="shadow: approved")

        await asyncio.to_thread(self._log_sync, req, GateDecision.APPROVE, "forward pending")
        status, body, detail = await self._forward_upstream(req)
        await self._log_async(req, GateDecision.APPROVE, detail, upstream_status=status)
        return ProxyResponse(
            decision=GateDecision.APPROVE,
            reason=detail,
            upstream_status=status,
            upstream_body=body,
        )

    def _payload(self, req: ProxyRequest, decision: GateDecision, detail: str, **extra: Any) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "client_id": req.client_id,
            "method": req.method,
            "path": req.path,
            "decision": decision.value,
            "detail": detail,
            "body_keys": sorted(req.body.keys()),
        }
        payload.update(extra)
        return payload

    def _log_sync(self, req: ProxyRequest, decision: GateDecision, detail: str, **extra: Any) -> None:
        if self.ledger is None:
            return
        self.ledger.append(
            event_type="proxy_request",
            payload=self._payload(req, decision, detail, **extra),
            manifest_id=f"proxy:{req.client_id}:{req.method}:{req.path}",
        )

    async def _log_async(
        self,
        req: ProxyRequest,
        decision: GateDecision,
        detail: str,
        **extra: Any,
    ) -> None:
        if self.ledger is None:
            return

        def _append() -> None:
            self.ledger.append(
                event_type="proxy_request",
                payload=self._payload(req, decision, detail, **extra),
                manifest_id=f"proxy:{req.client_id}:{req.method}:{req.path}",
            )

        await asyncio.to_thread(_append)

    async def _forward_upstream(
        self,
        req: ProxyRequest,
    ) -> tuple[int, dict[str, Any] | None, str]:
        base = self.upstream_base.rstrip("/")
        if not base:
            return 502, {"error": "PROXY_RISK_UPSTREAM_BASE not configured"}, "upstream: base URL missing"

        url = f"{base}{req.path}"
        headers: dict[str, str] = {"Content-Type": "application/json"}
        headers.update(self.vault.get_upstream_header("upstream"))
        if "Authorization" not in headers:
            headers.update(self.vault.get_upstream_header(req.client_id))

        try:
            async with httpx.AsyncClient(limits=_UPSTREAM_LIMITS, timeout=_UPSTREAM_TIMEOUT) as client:
                resp = await client.request(
                    req.method.upper(),
                    url,
                    json=req.body if req.body else None,
                    headers=headers,
                )
                try:
                    body: dict[str, Any] | None = resp.json()
                except (json.JSONDecodeError, ValueError):
                    body = {"raw": resp.text[:4096]}
                return resp.status_code, body, f"forwarded status={resp.status_code}"
        except httpx.RequestError as exc:
            return 502, {"error": str(exc)}, f"upstream error: {exc}"


async def serve_shadow_demo(
    *,
    host: str = "127.0.0.1",
    port: int = 18443,
    shadow_mode: bool = True,
    database: str = "data/proxy_risk_ledger.sqlite",
) -> None:
    """Minimal async demo — health + evaluate endpoint."""
    try:
        from aiohttp import web
    except ImportError as exc:
        raise RuntimeError("proxy-risk serve requires: pip install hibs-racing[instpp]") from exc

    ledger = AppendOnlyLedger(database, async_writes=True)
    ledger.start_async_writer()
    gw = ProxyRiskGateway(ledger=ledger, shadow_mode=shadow_mode)

    async def health(_: web.Request) -> web.Response:
        return web.json_response(
            {
                "ok": True,
                "mode": "shadow" if shadow_mode else "live",
                "upstream_base": gw.upstream_base or None,
            }
        )

    async def evaluate(request: web.Request) -> web.Response:
        body = await request.json()
        req = ProxyRequest(
            client_id=str(body.get("client_id") or "anon"),
            method=str(body.get("method") or "POST"),
            path=str(body.get("path") or "/"),
            body=body.get("body") or {},
            idempotency_key=body.get("idempotency_key"),
            reference_price=body.get("reference_price"),
        )
        resp = await gw.evaluate(req)
        return web.json_response(
            {
                "decision": resp.decision.value,
                "reason": resp.reason,
                "upstream_status": resp.upstream_status,
                "upstream_body": resp.upstream_body,
            }
        )

    app = web.Application()
    app.router.add_get("/health", health)
    app.router.add_post("/evaluate", evaluate)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    mode = "shadow" if shadow_mode else "live"
    print(f"proxy-risk {mode} listening on http://{host}:{port}")
    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        ledger.stop_async_writer(flush=True)
        await runner.cleanup()
