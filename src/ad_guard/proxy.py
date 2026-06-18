"""Outbound marketing API guard — spend velocity + cryptographic audit."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any

from inst_spine.gates.circuit import CircuitBreaker, CredentialVault
from inst_spine.ledger import AppendOnlyLedger, IdempotencyGuard
from inst_spine.rates import TokenBucket, ZScoreConfig, ZScoreDriftDetector, token_bucket_backend_from_env

from ad_guard.spend import extract_spend_metrics
from proxy_risk.router import GateDecision, ProxyResponse


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
      circuit → schema → per-campaign token bucket → idempotency → Z-score on spend
    Cold path: async ledger append (WAL + genesis chain).

    NOT a pre-bid RTB verifier (DoubleVerify/IAS territory).
    NOT an LLM safety firewall (NeMo/Llama/Bedrock territory).
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
    ) -> None:
        self.ledger = ledger
        self._rate_backend = rate_backend or token_bucket_backend_from_env()
        self._bucket_capacity = bucket_capacity
        self._bucket_refill = bucket_refill
        self._z_config = z_config or ZScoreConfig(window=20, z_max=3.0)
        self._drift_by_campaign: dict[str, ZScoreDriftDetector] = {}
        self.circuit = circuit or CircuitBreaker()
        self.vault = vault or CredentialVault()
        self.shadow_mode = shadow_mode
        self.idempotency = IdempotencyGuard()

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
            return ProxyResponse(decision=GateDecision.KILL, reason=reason)

        if not req.client_id or not req.method or not req.path:
            return ProxyResponse(decision=GateDecision.REJECT, reason="schema: missing required fields")

        campaign_id, bid_amount, spend_delta = extract_spend_metrics(
            req.body, provider=req.provider
        )
        if req.campaign_id:
            campaign_id = req.campaign_id

        bucket = TokenBucket(
            capacity=self._bucket_capacity,
            refill_rate=self._bucket_refill,
            key=f"ad:campaign:{campaign_id}",
            backend=self._rate_backend,
        )
        if not bucket.consume(1.0):
            return ProxyResponse(
                decision=GateDecision.REJECT,
                reason=f"token_bucket: campaign {campaign_id} rate exceeded",
            )

        idem_key = req.idempotency_key or (
            f"{req.client_id}:{campaign_id}:{req.method}:{req.path}:"
            f"{json.dumps(req.body, sort_keys=True)}"
        )
        if not self.idempotency.check_and_set(idem_key):
            return ProxyResponse(decision=GateDecision.REJECT, reason="idempotency: duplicate request")

        spend_signal = spend_delta if spend_delta is not None else bid_amount
        if spend_signal is not None:
            drift = self._drift_for(campaign_id)
            anomaly, z = drift.is_anomaly(spend_signal)
            if anomaly:
                self.circuit.kill(
                    f"spend anomaly campaign={campaign_id} |Z|>{drift.z_max} (z={z:.2f})"
                )
                await self._log_async(
                    req,
                    campaign_id,
                    GateDecision.KILL,
                    f"z_score spend z={z:.2f}",
                    spend_signal=spend_signal,
                )
                return ProxyResponse(
                    decision=GateDecision.KILL,
                    reason=f"spend_drift: campaign={campaign_id} z={z:.2f}",
                )

        detail = "shadow forward" if self.shadow_mode else "forward"
        await self._log_async(req, campaign_id, GateDecision.APPROVE, detail, spend_signal=spend_signal)
        return ProxyResponse(
            decision=GateDecision.APPROVE,
            reason="shadow: approved" if self.shadow_mode else "approved",
            upstream_status=200 if not self.shadow_mode else None,
            upstream_body={"ok": True, "ad_guard": True, "campaign_id": campaign_id},
        )

    async def _log_async(
        self,
        req: AdSpendRequest,
        campaign_id: str,
        decision: GateDecision,
        detail: str,
        *,
        spend_signal: float | None = None,
    ) -> None:
        if self.ledger is None:
            return
        _, bid_amount, spend_delta = extract_spend_metrics(req.body, provider=req.provider)
        payload = {
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

        def _append() -> None:
            self.ledger.append(event_type="ad_spend_request", payload=payload)

        await asyncio.to_thread(_append)
