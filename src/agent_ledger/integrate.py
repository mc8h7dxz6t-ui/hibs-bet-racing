"""Drop-in hooks for LangChain / custom agent runtimes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_ledger.gate import AgentActionGate, AgentActionRequest, AgentActionResponse
from agent_ledger.policy import ToolPolicy


def authorize_tool_call(
    *,
    agent_id: str,
    tool_name: str,
    arguments: dict[str, Any],
    ledger_db: Path,
    permit_db: Path | None = None,
    session_id: str = "",
    idempotency_key: str | None = None,
    policy: ToolPolicy | None = None,
) -> dict[str, Any]:
    """
    Call before executing any agent tool:
      result = authorize_tool_call(...)
      if result['decision'] != 'permit': raise ToolNotAllowed
      # ... invoke tool ...
      complete_tool_call(permit_id=result['permit_id'], ...)
    """
    from agent_ledger.gate import gate_from_paths

    gw = gate_from_paths(ledger_db=ledger_db, permit_db=permit_db, policy=policy)
    resp = gw.authorize(
        AgentActionRequest(
            agent_id=agent_id,
            tool_name=tool_name,
            arguments=arguments,
            session_id=session_id,
            idempotency_key=idempotency_key,
        )
    )
    return resp.to_dict()


def complete_tool_call(
    *,
    permit_id: str,
    result: Any,
    ledger_db: Path,
    permit_db: Path | None = None,
    policy: ToolPolicy | None = None,
) -> dict[str, Any]:
    from agent_ledger.gate import gate_from_paths

    gw = gate_from_paths(ledger_db=ledger_db, permit_db=permit_db, policy=policy)
    resp = gw.complete(permit_id, result=result)
    return resp.to_dict()
