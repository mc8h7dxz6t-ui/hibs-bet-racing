"""Agent Ledger export — observation-lane permit redaction."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from inst_spine.export import AuditBundleResult, build_audit_bundle


def redact_permit_entry(entry: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(entry)
    payload = out.get("payload")
    if not isinstance(payload, dict) or out.get("event_type") != "agent_action":
        return out
    args = payload.get("arguments")
    if isinstance(args, dict):
        payload = dict(payload)
        payload["arguments_redacted"] = True
        payload["argument_keys"] = sorted(args.keys())
        payload.pop("arguments", None)
        out["payload"] = payload
    return out


def redact_permit_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [redact_permit_entry(e) for e in entries]


def build_agent_ledger_audit_bundle(
    database: Path,
    *,
    out_dir: Path | None = None,
    tarball_path: Path | None = None,
    observation_lane: bool = True,
    product: str = "agent-ledger",
) -> AuditBundleResult:
    return build_audit_bundle(
        database,
        out_dir=out_dir,
        tarball_path=tarball_path,
        product=product,
        observation_lane=observation_lane,
    )
