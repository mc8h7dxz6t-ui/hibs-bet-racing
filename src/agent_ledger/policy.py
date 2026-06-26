"""Tool policy — risk tiers, allowlists, argument guards."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class RiskTier(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# Default institutional tool taxonomy (buyers extend via policy file).
DEFAULT_TOOL_RISK: dict[str, RiskTier] = {
    "read_file": RiskTier.LOW,
    "search_docs": RiskTier.LOW,
    "list_records": RiskTier.LOW,
    "write_file": RiskTier.MEDIUM,
    "http_get": RiskTier.MEDIUM,
    "sql_select": RiskTier.MEDIUM,
    "http_post": RiskTier.HIGH,
    "sql_write": RiskTier.HIGH,
    "send_email": RiskTier.HIGH,
    "transfer_funds": RiskTier.CRITICAL,
    "delete_production": RiskTier.CRITICAL,
    "deploy_service": RiskTier.CRITICAL,
}

FORBIDDEN_ARG_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("sql_injection", re.compile(r"(?i)\b(DROP|TRUNCATE|DELETE\s+FROM)\b")),
    ("path_traversal", re.compile(r"\.\./")),
    ("shell_metachar", re.compile(r"[;|`$]")),
]

AGENT_TIER_CEILING: dict[str, RiskTier] = {
    "sandbox": RiskTier.LOW,
    "standard": RiskTier.MEDIUM,
    "privileged": RiskTier.HIGH,
    "break_glass": RiskTier.CRITICAL,
}


@dataclass
class ToolPolicy:
    """Fail-closed policy for agent tool invocations."""

    allowed_tools: frozenset[str] = field(default_factory=lambda: frozenset(DEFAULT_TOOL_RISK.keys()))
    tool_risk: dict[str, RiskTier] = field(default_factory=lambda: dict(DEFAULT_TOOL_RISK))
    agent_tier: str = "standard"
    require_human_for_critical: bool = True
    shadow_mode: bool = False

    @classmethod
    def from_file(cls, path: Path) -> ToolPolicy:
        data = json.loads(path.read_text(encoding="utf-8"))
        tool_risk = {
            k: RiskTier(v) for k, v in (data.get("tool_risk") or DEFAULT_TOOL_RISK).items()
        }
        return cls(
            allowed_tools=frozenset(data.get("allowed_tools") or tool_risk.keys()),
            tool_risk=tool_risk,
            agent_tier=str(data.get("agent_tier") or "standard"),
            require_human_for_critical=bool(data.get("require_human_for_critical", True)),
            shadow_mode=bool(data.get("shadow_mode", False)),
        )

    def ceiling(self) -> RiskTier:
        return AGENT_TIER_CEILING.get(self.agent_tier, RiskTier.MEDIUM)

    def tool_tier(self, tool_name: str) -> RiskTier:
        return self.tool_risk.get(tool_name, RiskTier.HIGH)

    def evaluate_args(self, tool_name: str, arguments: dict[str, Any]) -> tuple[bool, str]:
        blob = json.dumps(arguments, sort_keys=True, default=str)
        for label, pattern in FORBIDDEN_ARG_PATTERNS:
            if pattern.search(blob):
                return False, f"forbidden_argument:{label}"
        if tool_name == "write_file":
            path = str(arguments.get("path") or "")
            if path.startswith("/etc") or path.startswith("/root"):
                return False, "forbidden_path"
        return True, "args_ok"

    def evaluate_tool(self, tool_name: str, arguments: dict[str, Any]) -> tuple[str, str]:
        """
        Returns (decision, reason) where decision is permit | deny | escalate.
        """
        name = (tool_name or "").strip()
        if not name:
            return "deny", "missing_tool_name"
        if name not in self.allowed_tools:
            return "deny", f"tool_not_allowlisted:{name}"

        ok, reason = self.evaluate_args(name, arguments)
        if not ok:
            return "deny", reason

        risk = self.tool_tier(name)
        ceiling = self.ceiling()
        tier_order = [RiskTier.LOW, RiskTier.MEDIUM, RiskTier.HIGH, RiskTier.CRITICAL]
        if tier_order.index(risk) > tier_order.index(ceiling):
            return "deny", f"tier_exceeds_agent_ceiling:{risk.value}>{ceiling.value}"

        if risk == RiskTier.CRITICAL and self.require_human_for_critical:
            if not arguments.get("human_approved"):
                return "escalate", "critical_tool_requires_human_approval"

        if self.shadow_mode:
            return "permit", f"shadow:would_permit:{risk.value}"
        return "permit", f"permitted:{risk.value}"
