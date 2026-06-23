"""Outbound marketing API guard — spend velocity + cryptographic audit."""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field
from typing import Any

import httpx

from inst_spine.gates.circuit import CircuitBreaker, CredentialVault
from inst_spine.ledger import AppendOnlyLedger
from inst_spine.rates import (
    IdempotencyBackend,
    TokenBucket,
    ZScoreConfig,
    ZScoreDriftDetector,
    idempotency_backend_from_env,
    token_bucket_backend_from_env,
)

from ad_guard.spend import extract_spend_metrics
from proxy_risk.router import GateDecision, ProxyResponse

_UPSTREAM_TIMEOUT = httpx.Timeout(5.0, connect=2.0)


@dataclass
class AdSpendRequest:
    """Outbound marketing API call under institutional spend guard."""

    client_id: str
    method: str
    path: str
    body: dict[str, Any] = field(default_factory=dict)
    provider: str = "generic"
    campaign_id: str | None = None
    idempotency_key: str | None = None


class AdGuardGateway:
    """
    Institutional spend firewall — sits between locked creative assets and DSP/API calls.

    Hot path (<10ms, memory only):
      circuit → schema → per-campaign token bucket → idempotency → Z-score on spend → forward
    Cold path: async ledger append on every gate outcome (WAL + genesis chain).
    """

    def __init__(
        self,
        *,
        ledger: AppendOnlyLedger | None = None,
        bucket_capacity: float = 60.0,
        bucket_refill: float = 10.0,
        z_config: ZScoreConfig | None = None,
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
        self._z_config = z_config or ZScoreConfig(window=20, z_max=3.0)
        self._drift_by_campaign: dict[str, ZScoreDriftDetector] = {}
        self.circuit = circuit or CircuitBreaker.from_env()
        self.vault = vault or CredentialVault()
        token = os.environ.get("AD_GUARD_UPSTREAM_TOKEN", "").strip()
        if token:
            self.vault.set_secret("upstream", token)
        self.shadow_mode = shadow_mode
        self.idempotency = idempotency or idempotency_backend_from_env()
        self.upstream_base = (upstream_base or os.environ.get("AD_GUARD_UPSTREAM_BASE", "")).strip()
        self.idempotency_ttl_sec = idempotency_ttl_sec

    def _drift_for(self, campaign_id: str) -> ZScoreDriftDetector:
        if campaign_id not in self._drift_by_campaign:
            cfg = ZScoreConfig(
                window=self._z_config.window,
                z_max=self._z_config.z_max,
                asset_id=campaign_id,
            )
            self._drift_by_campaign[campaign_id] = ZScoreDriftDetector.from_config(cfg)
        return self._drift_by_campaign[campaign_id]

    async def evaluate(self, req: AdSpendRequest) -> ProxyResponse:
        allowed, reason = self.circuit.allows_traffic()
        if not allowed:
            return await self._finish(req, "", GateDecision.KILL, reason)

        if not req.client_id or not req.method or not req.path:
            return await self._finish(req, "", GateDecision.REJECT, "schema: missing required fields")

        campaign_id, bid_amount, spend_delta = extract_spend_metrics(req.body, provider=req.provider)
        if req.campaign_id:
            campaign_id = req.campaign_id

        bucket = TokenBucket(
            capacity=self._bucket_capacity,
            refill_rate=self._bucket_refill,
            key=f"ad:campaign:{campaign_id}",
            backend=self._rate_backend,
        )
        if not bucket.consume(1.0):
            return await self._finish(
                req,
                campaign_id,
                GateDecision.REJECT,
                f"token_bucket: campaign {campaign_id} rate exceeded",
            )

        idem_key = req.idempotency_key or (
            f"{req.client_id}:{campaign_id}:{req.method}:{req.path}:"
            f"{json.dumps(req.body, sort_keys=True)}"
        )
        if not await self.idempotency.consume_idempotency_token(idem_key, self.idempotency_ttl_sec):
            return await self._finish(req, campaign_id, GateDecision.REJECT, "idempotency: duplicate request")

        spend_signal = spend_delta if spend_delta is not None else bid_amount
        if spend_signal is not None:
            drift = self._drift_for(campaign_id)
            anomaly, z = drift.is_anomaly(spend_signal)
            if anomaly:
                self.circuit.kill(
                    f"spend anomaly campaign={campaign_id} |Z|>{drift.z_max} (z={z:.2f})"
                )
                return await self._finish(
                    req,
                    campaign_id,
                    GateDecision.KILL,
                    f"spend_drift: campaign={campaign_id} z={z:.2f}",
                    spend_signal=spend_signal,
                )

        if self.shadow_mode:
            return await self._finish(
                req,
                campaign_id,
                GateDecision.APPROVE,
                "shadow: approved",
                spend_signal=spend_signal,
            )

        status, body, detail = await self._forward_upstream(req)
        if status < 200 or status >= 400:
            return await self._finish(
                req,
                campaign_id,
                GateDecision.REJECT,
                detail,
                spend_signal=spend_signal,
                upstream_status=status,
                upstream_body=body,
            )
        return await self._finish(
            req,
            campaign_id,
            GateDecision.APPROVE,
            detail,
            spend_signal=spend_signal,
            upstream_status=status,
            upstream_body=body,
        )

    async def _forward_upstream(self, req: AdSpendRequest) -> tuple[int, dict[str, Any], str]:
        if not self.upstream_base:
            return 503, {}, "upstream: AD_GUARD_UPSTREAM_BASE not configured"
        url = self.upstream_base.rstrip("/") + req.path
        headers: dict[str, str] = {"Content-Type": "application/json"}
        token = self.vault.get_secret("upstream")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            async with httpx.AsyncClient(timeout=_UPSTREAM_TIMEOUT) as client:
                resp = await client.request(req.method.upper(), url, json=req.body, headers=headers)
            try:
                body = resp.json() if resp.content else {}
            except json.JSONDecodeError:
                body = {"raw": resp.text[:500]}
            return resp.status_code, body, f"upstream: {resp.status_code}"
        except httpx.HTTPError as exc:
            return 503, {}, f"upstream: {exc}"

    async def _finish(
        self,
        req: AdSpendRequest,
        campaign_id: str,
        decision: GateDecision,
        detail: str,
        *,
        spend_signal: float | None = None,
        upstream_status: int | None = None,
        upstream_body: dict[str, Any] | None = None,
    ) -> ProxyResponse:
        await self._log_async(
            req,
            campaign_id,
            decision,
            detail,
            spend_signal=spend_signal,
            upstream_status=upstream_status,
            upstream_body=upstream_body,
        )
        return ProxyResponse(
            decision=decision,
            reason=detail,
            upstream_status=upstream_status,
            upstream_body=upstream_body,
        )

    async def _log_async(
        self,
        req: AdSpendRequest,
        campaign_id: str,
        decision: GateDecision,
        detail: str,
        *,
        spend_signal: float | None = None,
        upstream_status: int | None = None,
        upstream_body: dict[str, Any] | None = None,
    ) -> None:
        if self.ledger is None:
            return
        _, bid_amount, spend_delta = extract_spend_metrics(req.body, provider=req.provider)
        payload: dict[str, Any] = {
            "client_id": req.client_id,
            "campaign_id": campaign_id,
            "provider": req.provider,
            "method": req.method,
            "path": req.path,
            "decision": decision.value,
            "detail": detail,
            "bid_amount": bid_amount,
            "spend_delta": spend_delta,
            "spend_signal": spend_signal,
            "body_keys": sorted(req.body.keys()),
        }
        if upstream_status is not None:
            payload["upstream_status"] = upstream_status
        if upstream_body is not None:
            payload["upstream_body"] = upstream_body

        def _append() -> None:
            self.ledger.append(event_type="ad_spend_request", payload=payload)

        await asyncio.to_thread(_append)
