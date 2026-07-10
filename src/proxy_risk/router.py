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
_ALLOWED_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE"})


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
    model_features: dict[str, float] | None = None
    estimated_cost: float | None = None


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
    Cold path: ledger append on every gate outcome (full audit trail).
    Live mode: sync WAL before upstream; upstream 4xx/5xx → REJECT (fail-closed).
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
        drift_baseline_path: str | None = None,
        drift_mode: str | None = None,
        spend_wallet_db: str | None = None,
        spend_ledger_db: str | None = None,
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
        self._drift_gate = None
        self._drift_rolling = None
        baseline = (drift_baseline_path or os.environ.get("PROXY_DRIFT_BASELINE", "")).strip()
        if baseline:
            from pathlib import Path

            from drift_gate.baseline import FeatureBaseline
            from drift_gate.gate import DriftGate, DriftGateConfig, DriftGateMode
            from drift_gate.state import RollingStateStore

            mode = (drift_mode or os.environ.get("PROXY_DRIFT_MODE", "shadow")).strip()
            bl = FeatureBaseline.load(Path(baseline))
            self._drift_rolling = RollingStateStore.from_baseline(
                Path(baseline),
                redis_key=f"proxy:{bl.model_id}",
            )
            self._drift_gate = DriftGate(
                bl,
                config=DriftGateConfig(mode=DriftGateMode(mode)),
                rolling_window=self._drift_rolling.as_dict(),
            )

        self._spend_wallet_db = (
            spend_wallet_db or os.environ.get("PROXY_SPEND_WALLET_DB", "")
        ).strip()
        self._spend_ledger_db = (
            spend_ledger_db or os.environ.get("PROXY_SPEND_LEDGER_DB", "")
        ).strip()

    async def evaluate(self, req: ProxyRequest) -> ProxyResponse:
        """Hot-path gate evaluation — every outcome logged when ledger attached."""
        allowed, reason = self.circuit.allows_traffic()
        if not allowed:
            await self._log_circuit_event(req, reason)
            return await self._finish(req, GateDecision.KILL, reason)

        if not req.client_id or not req.method or not req.path:
            return await self._finish(req, GateDecision.REJECT, "schema: missing required fields")

        method = req.method.upper()
        if method not in _ALLOWED_METHODS:
            return await self._finish(req, GateDecision.REJECT, f"schema: method {method!r} not allowed")

        bucket = self.bucket or TokenBucket(
            capacity=self._bucket_capacity,
            refill_rate=self._bucket_refill,
            key=f"proxy:{req.client_id}",
            backend=self._rate_backend,
        )
        if not bucket.consume(1.0):
            return await self._finish(req, GateDecision.REJECT, "token_bucket: rate exceeded")

        idem_key = req.idempotency_key or (
            f"{req.client_id}:{req.method}:{req.path}:{json.dumps(req.body, sort_keys=True)}"
        )
        if not await self.idempotency.consume_idempotency_token(idem_key, self.idempotency_ttl_sec):
            return await self._finish(req, GateDecision.REJECT, "idempotency: duplicate request")

        if req.reference_price is not None:
            anomaly, z = self.drift.is_anomaly(req.reference_price)
            if anomaly:
                self.circuit.kill(f"z_score drift |Z|>{self.drift.z_max} (z={z:.2f})")
                await self._log_circuit_event(req, self.circuit.reason)
                return await self._finish(req, GateDecision.KILL, f"drift: z={z:.2f}")

        features = req.model_features
        if features is None and isinstance(req.body.get("features"), dict):
            try:
                features = {k: float(v) for k, v in req.body["features"].items()}
            except (TypeError, ValueError):
                features = None
        if self._drift_gate is not None and features:
            from drift_gate.gate import DriftGateDecision, DriftGateRequest
            from drift_gate.record import record_drift_evaluation

            dg_req = DriftGateRequest(
                model_id=self._drift_gate.baseline.model_id,
                version=self._drift_gate.baseline.version,
                feature_vector=features,
                request_id=idem_key,
            )
            dg_resp = self._drift_gate.evaluate(dg_req)
            if self._drift_rolling is not None:
                self._drift_rolling._data = self._drift_gate._rolling
                self._drift_rolling.save()
            if self.ledger is not None:
                await asyncio.to_thread(
                    record_drift_evaluation,
                    request=dg_req,
                    response=dg_resp,
                    database=self.ledger.database,
                )
            if dg_resp.decision in (DriftGateDecision.REJECT, DriftGateDecision.KILL):
                decision = GateDecision.KILL if dg_resp.decision == DriftGateDecision.KILL else GateDecision.REJECT
                return await self._finish(req, decision, f"drift_gate: {dg_resp.reason}")

        if self.shadow_mode:
            return await self._finish(req, GateDecision.APPROVE, "shadow: approved")

        hold_id: str | None = None
        spend_request_id = idem_key
        est_cost = self._estimated_cost(req)
        if self._spend_wallet_db and est_cost > 0:
            hold_id, spend_err = await asyncio.to_thread(
                self._reserve_spend, spend_request_id, est_cost
            )
            if hold_id is None:
                return await self._finish(req, GateDecision.REJECT, f"spend_guard: {spend_err}")

        await asyncio.to_thread(self._log_sync, req, GateDecision.APPROVE, "forward pending")
        status, body, detail = await self._forward_upstream(req)
        if status < 200 or status >= 400:
            if hold_id and self._spend_wallet_db:
                await asyncio.to_thread(self._release_spend, hold_id)
            self.circuit.record_failure(detail)
            await self._log_circuit_event(req, f"upstream_failure:{detail}")
            return await self._finish(
                req,
                GateDecision.REJECT,
                detail,
                upstream_status=status,
                upstream_body=body,
            )

        self.circuit.record_success()

        if hold_id and self._spend_wallet_db:
            actual = self._actual_cost(body, est_cost)
            await asyncio.to_thread(self._settle_spend, hold_id, spend_request_id, actual)

        return await self._finish(
            req,
            GateDecision.APPROVE,
            detail,
            upstream_status=status,
            upstream_body=body,
        )

    async def _finish(
        self,
        req: ProxyRequest,
        decision: GateDecision,
        detail: str,
        *,
        upstream_status: int | None = None,
        upstream_body: dict[str, Any] | None = None,
        sync_only: bool = False,
    ) -> ProxyResponse:
        extra: dict[str, Any] = {}
        if upstream_status is not None:
            extra["upstream_status"] = upstream_status
        if upstream_body is not None:
            extra["upstream_body"] = upstream_body
        if sync_only:
            self._log_sync(req, decision, detail, **extra)
        else:
            await self._log_async(req, decision, detail, **extra)
        return ProxyResponse(
            decision=decision,
            reason=detail,
            upstream_status=upstream_status,
            upstream_body=upstream_body,
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

    async def _log_circuit_event(self, req: ProxyRequest, reason: str) -> None:
        if self.ledger is None:
            return
        payload = {
            "client_id": req.client_id,
            "circuit_state": self.circuit.state.value,
            "reason": reason,
            "method": req.method,
            "path": req.path,
            **self.circuit.transition_snapshot(),
        }

        def _append() -> None:
            self.ledger.append(
                event_type="circuit_breaker",
                payload=payload,
                manifest_id=f"circuit:{req.client_id}",
                metadata={"product": "proxy-risk"},
            )

        await asyncio.to_thread(_append)

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

    def _estimated_cost(self, req: ProxyRequest) -> float:
        if req.estimated_cost is not None:
            return float(req.estimated_cost)
        raw = req.body.get("estimated_cost", req.body.get("spend_estimate"))
        try:
            return float(raw) if raw is not None else 0.0
        except (TypeError, ValueError):
            return 0.0

    def _actual_cost(self, body: dict[str, Any] | None, fallback: float) -> float:
        if not body:
            return fallback
        for key in ("actual_cost", "cost", "spend"):
            if key in body:
                try:
                    return float(body[key])
                except (TypeError, ValueError):
                    pass
        return fallback

    def _reserve_spend(self, request_id: str, amount: float) -> tuple[str | None, str]:
        from pathlib import Path

        from spend_guard.integrate import reserve_api_call

        result = reserve_api_call(
            request_id=request_id,
            estimated_cost=amount,
            wallet_db=Path(self._spend_wallet_db),
            ledger_db=Path(self._spend_ledger_db) if self._spend_ledger_db else None,
            service="proxy-risk",
        )
        if result.get("decision") != "approve":
            return None, str(result.get("reason") or "reserve_denied")
        return str(result.get("hold_id") or ""), ""

    def _settle_spend(self, hold_id: str, request_id: str, actual: float) -> None:
        from pathlib import Path

        from spend_guard.integrate import settle_api_call

        settle_api_call(
            hold_id=hold_id,
            actual_cost=actual,
            request_id=request_id,
            wallet_db=Path(self._spend_wallet_db),
            ledger_db=Path(self._spend_ledger_db) if self._spend_ledger_db else None,
            service="proxy-risk",
        )

    def _release_spend(self, hold_id: str) -> None:
        from pathlib import Path

        from spend_guard.wallet import SpendWallet

        SpendWallet(Path(self._spend_wallet_db)).release(hold_id)


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
    api_token = os.environ.get("PROXY_RISK_API_TOKEN", "").strip()

    async def health(_: web.Request) -> web.Response:
        return web.json_response(
            {
                "ok": True,
                "mode": "shadow" if shadow_mode else "live",
                "upstream_base": gw.upstream_base or None,
                "auth_required": bool(api_token),
            }
        )

    async def evaluate(request: web.Request) -> web.Response:
        if request.method != "POST":
            return web.json_response(
                {"ok": False, "error": {"code": "METHOD_NOT_ALLOWED", "message": "POST only"}},
                status=405,
            )
        if api_token:
            auth = request.headers.get("Authorization", "")
            if auth != f"Bearer {api_token}":
                return web.json_response(
                    {"ok": False, "error": {"code": "UNAUTHORIZED", "message": "invalid bearer token"}},
                    status=401,
                )
        try:
            body = await request.json()
        except (json.JSONDecodeError, ValueError):
            return web.json_response(
                {"ok": False, "error": {"code": "INVALID_JSON", "message": "request body must be JSON"}},
                status=400,
            )
        if not isinstance(body, dict):
            return web.json_response(
                {"ok": False, "error": {"code": "INVALID_JSON", "message": "JSON object required"}},
                status=400,
            )
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
