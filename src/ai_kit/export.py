"""AI Kit trace export — observation-lane redaction for enterprise buyers."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from inst_spine.export import AuditBundleResult, build_audit_bundle


def redact_trace_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """Strip raw prompts/completions; keep cryptographic summaries on chain."""
    out = copy.deepcopy(entry)
    payload = out.get("payload")
    if not isinstance(payload, dict):
        return out
    if out.get("event_type") not in ("agent_trace", "agent_step", "checkpoint"):
        return out
    redacted = dict(payload)
    for key in ("prompt", "completion", "raw_response", "messages", "tool_output"):
        if key in redacted:
            raw = redacted.pop(key)
            if raw is not None:
                canonical = json.dumps(raw, sort_keys=True, default=str, separators=(",", ":"))
                redacted[f"{key}_sha256"] = hashlib.sha256(canonical.encode()).hexdigest()
    redacted["trace_redacted"] = True
    out["payload"] = redacted
    return out


def redact_trace_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [redact_trace_entry(e) for e in entries]


def build_ai_kit_audit_bundle(
    database: Path,
    *,
    out_dir: Path | None = None,
    tarball_path: Path | None = None,
    observation_lane: bool = False,
    repro_run: bool = False,
    product: str = "ai-kit",
) -> AuditBundleResult:
    lane = observation_lane or __import__("os").getenv("INST_EXPORT_OBSERVATION_LANE", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    return build_audit_bundle(
        database,
        out_dir=out_dir,
        tarball_path=tarball_path,
        repro_run=repro_run,
        product=product,
        observation_lane=lane,
    )
