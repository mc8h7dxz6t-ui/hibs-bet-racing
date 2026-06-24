"""Agent action gate — authorize before tool invoke, attest after."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from agent_ledger.permits import PermitStore
from agent_ledger.policy import ToolPolicy
from inst_spine.contracts import stable_id
from inst_spine.ledger import AppendOnlyLedger


class ActionDecision(str, Enum):
    PERMIT = "permit"
    DENY = "deny"
    ESCALATE = "escalate"


@dataclass
class AgentActionRequest:
    agent_id: str
    tool_name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    session_id: str = ""
    idempotency_key: str | None = None


@dataclass
class AgentActionResponse:
    decision: ActionDecision
    reason: str
    permit_id: str | None = None
    shadow: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.value,
            "reason": self.reason,
            "permit_id": self.permit_id,
            "shadow": self.shadow,
        }


class AgentActionGate:
    """
    Runtime governance for AI agent tool calls.

    ModelGovernor proves *which model* was approved; Agent Ledger proves
    *which actions* were permitted before execution.
    """

    def __init__(
        self,
        *,
        policy: ToolPolicy | None = None,
        ledger: AppendOnlyLedger | None = None,
        permit_store: PermitStore | None = None,
    ) -> None:
        self.policy = policy or ToolPolicy()
        self.ledger = ledger
        self.permits = permit_store

    def authorize(self, req: AgentActionRequest) -> AgentActionResponse:
        if req.idempotency_key and self.permits:
            existing = self._find_by_idempotency(req)
            if existing:
                return existing

        decision, reason = self.policy.evaluate_tool(req.tool_name, req.arguments)
        act = ActionDecision(decision)
        permit_id: str | None = None

        if act == ActionDecision.PERMIT and self.permits and not self.policy.shadow_mode:
            rec = self.permits.create_permit(
                agent_id=req.agent_id,
                tool_name=req.tool_name,
                decision=act.value,
                reason=reason,
                permit_id=req.idempotency_key,
            )
            permit_id = rec.permit_id
        elif act == ActionDecision.PERMIT:
            permit_id = req.idempotency_key or stable_id(
                req.agent_id, req.tool_name, req.session_id, "permit"
            )

        resp = AgentActionResponse(
            decision=act,
            reason=reason,
            permit_id=permit_id,
            shadow=self.policy.shadow_mode,
        )
        self._log(req, resp, phase="authorize")
        return resp

    def complete(
        self,
        permit_id: str,
        *,
        result: Any,
        agent_id: str = "",
        tool_name: str = "",
    ) -> AgentActionResponse:
        if not self.permits:
            return AgentActionResponse(
                decision=ActionDecision.DENY,
                reason="permit_store_required",
            )
        rec = self.permits.get(permit_id)
        if rec is None:
            resp = AgentActionResponse(decision=ActionDecision.DENY, reason="permit_not_found")
            self._log_completion(permit_id, agent_id, tool_name, result, resp)
            return resp

        ok, reason = self.permits.complete(permit_id)
        if not ok:
            resp = AgentActionResponse(decision=ActionDecision.DENY, reason=reason, permit_id=permit_id)
            self._log_completion(permit_id, rec.agent_id, rec.tool_name, result, resp)
            return resp

        resp = AgentActionResponse(
            decision=ActionDecision.PERMIT,
            reason="attested",
            permit_id=permit_id,
        )
        self._log_completion(permit_id, rec.agent_id, rec.tool_name, result, resp)
        return resp

    def _find_by_idempotency(self, req: AgentActionRequest) -> AgentActionResponse | None:
        assert self.permits is not None
        if not req.idempotency_key:
            return None
        rec = self.permits.get(req.idempotency_key)
        if rec is None:
            return None
        return AgentActionResponse(
            decision=ActionDecision(rec.decision),
            reason=f"idempotent:{rec.reason}",
            permit_id=rec.permit_id,
        )

    def _log(self, req: AgentActionRequest, resp: AgentActionResponse, *, phase: str) -> None:
        if self.ledger is None:
            return
        manifest_id = req.idempotency_key or stable_id(
            req.agent_id, req.tool_name, req.session_id, phase
        )
        self.ledger.append(
            event_type="agent_action",
            payload={
                "phase": phase,
                "agent_id": req.agent_id,
                "tool_name": req.tool_name,
                "arguments": req.arguments,
                "session_id": req.session_id,
                "decision": resp.decision.value,
                "reason": resp.reason,
                "permit_id": resp.permit_id,
                "shadow": resp.shadow,
            },
            manifest_id=manifest_id,
            metadata={
                "product": "agent-ledger",
                "phase": phase,
                "agent_id": req.agent_id,
                "tool_name": req.tool_name,
            },
        )

    def _log_completion(
        self,
        permit_id: str,
        agent_id: str,
        tool_name: str,
        result: Any,
        resp: AgentActionResponse,
    ) -> None:
        if self.ledger is None:
            return
        result_bytes = (
            result if isinstance(result, (bytes, bytearray))
            else json.dumps(result, sort_keys=True, default=str).encode()
        )
        result_hash = hashlib.sha256(result_bytes).hexdigest()
        self.ledger.append(
            event_type="agent_action",
            payload={
                "phase": "complete",
                "permit_id": permit_id,
                "agent_id": agent_id,
                "tool_name": tool_name,
                "result_hash": result_hash,
                "decision": resp.decision.value,
                "reason": resp.reason,
            },
            manifest_id=stable_id(permit_id, "complete", result_hash[:16]),
            metadata={
                "product": "agent-ledger",
                "phase": "complete",
                "permit_id": permit_id,
            },
        )


def gate_from_paths(
    *,
    ledger_db: Path,
    permit_db: Path | None = None,
    policy: ToolPolicy | None = None,
) -> AgentActionGate:
    ledger = AppendOnlyLedger(ledger_db)
    permits = PermitStore(permit_db or ledger_db.with_name(ledger_db.stem + "_permits.sqlite"))
    return AgentActionGate(policy=policy, ledger=ledger, permit_store=permits)
