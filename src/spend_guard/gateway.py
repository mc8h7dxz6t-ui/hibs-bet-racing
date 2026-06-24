"""Spend guard gateway — reserve before API dispatch."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from inst_spine.ledger import AppendOnlyLedger
from spend_guard.wallet import SpendWallet


class SpendGuardDecision(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"
    LOCKED = "locked"


@dataclass
class SpendRequest:
    request_id: str
    estimated_cost: float
    service: str = "api"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SpendResponse:
    decision: SpendGuardDecision
    reason: str
    hold_id: str | None = None
    wallet: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.value,
            "reason": self.reason,
            "hold_id": self.hold_id,
            "wallet": self.wallet,
        }


class SpendGuardGateway:
    """
    Reserve-before-dispatch spend boundary.
    Pair with upstream API call: reserve → dispatch → settle(actual).
    """

    def __init__(
        self,
        wallet: SpendWallet,
        *,
        ledger: AppendOnlyLedger | None = None,
        shadow_mode: bool = False,
    ) -> None:
        self.wallet = wallet
        self.ledger = ledger
        self.shadow_mode = shadow_mode

    def reserve(self, req: SpendRequest) -> SpendResponse:
        state = self.wallet.get_state()
        if state.locked:
            resp = SpendResponse(
                decision=SpendGuardDecision.LOCKED,
                reason=state.lock_reason or "wallet_locked",
                wallet=state.__dict__,
            )
            self._log(req, resp, phase="reserve")
            return resp

        if self.shadow_mode:
            resp = SpendResponse(
                decision=SpendGuardDecision.APPROVE,
                reason="shadow:reserve_ok",
                hold_id=None,
                wallet=state.__dict__,
            )
            self._log(req, resp, phase="reserve")
            return resp

        ok, reason, hold_id = self.wallet.reserve(req.estimated_cost, request_id=req.request_id)
        if not ok:
            decision = SpendGuardDecision.LOCKED if "DRIFT" in reason or "locked" in reason else SpendGuardDecision.REJECT
            resp = SpendResponse(decision=decision, reason=reason, wallet=self.wallet.to_dict())
            self._log(req, resp, phase="reserve")
            return resp

        resp = SpendResponse(
            decision=SpendGuardDecision.APPROVE,
            reason="reserved",
            hold_id=hold_id,
            wallet=self.wallet.to_dict(),
        )
        self._log(req, resp, phase="reserve")
        return resp

    def settle(self, hold_id: str, *, actual_cost: float, request_id: str, service: str = "api") -> SpendResponse:
        if self.shadow_mode:
            resp = SpendResponse(
                decision=SpendGuardDecision.APPROVE,
                reason="shadow:settled",
                hold_id=hold_id,
                wallet=self.wallet.to_dict(),
            )
            self._log(
                SpendRequest(request_id=request_id, estimated_cost=actual_cost, service=service),
                resp,
                phase="settle",
            )
            return resp

        ok, reason = self.wallet.settle(hold_id, actual_amount=actual_cost)
        decision = SpendGuardDecision.LOCKED if "DRIFT" in reason else (
            SpendGuardDecision.APPROVE if ok else SpendGuardDecision.REJECT
        )
        resp = SpendResponse(decision=decision, reason=reason, hold_id=hold_id, wallet=self.wallet.to_dict())
        self._log(
            SpendRequest(request_id=request_id, estimated_cost=actual_cost, service=service),
            resp,
            phase="settle",
        )
        return resp

    def _log(self, req: SpendRequest, resp: SpendResponse, *, phase: str) -> None:
        if self.ledger is None:
            return
        self.ledger.append(
            event_type="spend_guard",
            payload={
                "phase": phase,
                "request_id": req.request_id,
                "service": req.service,
                "estimated_cost": req.estimated_cost,
                "decision": resp.decision.value,
                "reason": resp.reason,
                "hold_id": resp.hold_id,
                "metadata": req.metadata,
            },
            manifest_id=req.request_id,
            metadata={"product": "spend-guard", "phase": phase},
        )


def gateway_from_paths(
    *,
    wallet_db: Path,
    ledger_db: Path | None = None,
    initial_balance: float = 1000.0,
    shadow_mode: bool = False,
) -> SpendGuardGateway:
    wallet = SpendWallet(wallet_db, initial_balance=initial_balance)
    ledger = AppendOnlyLedger(ledger_db) if ledger_db else None
    return SpendGuardGateway(wallet=wallet, ledger=ledger, shadow_mode=shadow_mode)
