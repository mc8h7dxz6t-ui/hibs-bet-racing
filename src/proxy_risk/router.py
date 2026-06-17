"""Async proxy gateway — hot path memory only, cold path ledger."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from inst_spine.gates.circuit import CircuitBreaker, CredentialVault
from inst_spine.ledger import AppendOnlyLedger, IdempotencyGuard
from inst_spine.rates import TokenBucket, ZScoreDriftDetector


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
    circuit → schema → token bucket → idempotency → z-score drift
  Cold path: async ledger append (write-behind).
    """

    def __init__(
        self,
        *,
        ledger: AppendOnlyLedger | None = None,
        bucket: TokenBucket | None = None,
        drift: ZScoreDriftDetector | None = None,
        circuit: CircuitBreaker | None = None,
        vault: CredentialVault | None = None,
        shadow_mode: bool = True,
    ) -> None:
        self.ledger = ledger
        self.bucket = bucket or TokenBucket(capacity=30.0, refill_rate=5.0)
        self.drift = drift or ZScoreDriftDetector()
        self.circuit = circuit or CircuitBreaker()
        self.vault = vault or CredentialVault()
        self.shadow_mode = shadow_mode
        self.idempotency = IdempotencyGuard()
        self._required_fields = ("client_id", "method", "path")

    async def evaluate(self, req: ProxyRequest) -> ProxyResponse:
        """Hot-path gate evaluation — no disk I/O."""
        allowed, reason = self.circuit.allows_traffic()
        if not allowed:
            return ProxyResponse(decision=GateDecision.KILL, reason=reason)

        if not req.client_id or not req.method or not req.path:
            return ProxyResponse(decision=GateDecision.REJECT, reason="schema: missing required fields")

        if not self.bucket.consume(1.0):
            return ProxyResponse(decision=GateDecision.REJECT, reason="token_bucket: rate exceeded")

        idem_key = req.idempotency_key or f"{req.client_id}:{req.method}:{req.path}:{json.dumps(req.body, sort_keys=True)}"
        if not self.idempotency.check_and_set(idem_key):
            return ProxyResponse(decision=GateDecision.REJECT, reason="idempotency: duplicate request")

        if req.reference_price is not None:
            anomaly, z = self.drift.is_anomaly(req.reference_price)
            if anomaly:
                self.circuit.kill(f"z_score drift |Z|>{self.drift.z_max} (z={z:.2f})")
                return ProxyResponse(decision=GateDecision.KILL, reason=f"drift: z={z:.2f}")

        if self.shadow_mode:
            await self._log_async(req, GateDecision.APPROVE, "shadow forward")
            return ProxyResponse(decision=GateDecision.APPROVE, reason="shadow: approved")

        await self._log_async(req, GateDecision.APPROVE, "forward")
        return ProxyResponse(
            decision=GateDecision.APPROVE,
            reason="approved",
            upstream_status=200,
            upstream_body={"ok": True, "proxy": True},
        )

    async def _log_async(self, req: ProxyRequest, decision: GateDecision, detail: str) -> None:
        if self.ledger is None:
            return
        payload = {
            "client_id": req.client_id,
            "method": req.method,
            "path": req.path,
            "decision": decision.value,
            "detail": detail,
            "body_keys": sorted(req.body.keys()),
        }

        def _append() -> None:
            self.ledger.append(event_type="proxy_request", payload=payload)

        await asyncio.to_thread(_append)


async def serve_shadow_demo(*, host: str = "127.0.0.1", port: int = 18443) -> None:
    """Minimal async demo — health + evaluate endpoint."""
    try:
        from aiohttp import web
    except ImportError as exc:
        raise RuntimeError("proxy-risk serve requires: pip install hibs-racing[instpp]") from exc

    ledger = AppendOnlyLedger("data/proxy_risk_ledger.sqlite", async_writes=True)
    ledger.start_async_writer()
    gw = ProxyRiskGateway(ledger=ledger, shadow_mode=True)

    async def health(_: web.Request) -> web.Response:
        return web.json_response({"ok": True, "mode": "shadow"})

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
            }
        )

    app = web.Application()
    app.router.add_get("/health", health)
    app.router.add_post("/evaluate", evaluate)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    print(f"proxy-risk shadow listening on http://{host}:{port}")
    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        ledger.stop_async_writer(flush=True)
        await runner.cleanup()
