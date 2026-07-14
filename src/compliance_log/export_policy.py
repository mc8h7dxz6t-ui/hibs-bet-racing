"""Export policy manifest — embedded in compliance audit bundles."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def default_export_policy() -> dict[str, Any]:
    return {
        "protocol": "inst-compliance-export-policy-v1",
        "retention_years": int(os.getenv("INST_COMPLIANCE_RETENTION_YEARS", "7")),
        "redaction_mode": os.getenv("INST_COMPLIANCE_REDACTION_MODE", "none"),
        "observation_lane": os.getenv("INST_COMPLIANCE_OBSERVATION_LANE", "0") == "1",
        "jurisdiction": os.getenv("INST_COMPLIANCE_JURISDICTION", "UK"),
        "export_abort_on_gate_fail": True,
    }


def load_export_policy(path: Path | None = None) -> dict[str, Any]:
    if path is not None and path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    env_path = os.getenv("INST_COMPLIANCE_EXPORT_POLICY", "").strip()
    if env_path and Path(env_path).is_file():
        return json.loads(Path(env_path).read_text(encoding="utf-8"))
    return default_export_policy()


def write_policy_file(dest: Path, policy: dict[str, Any] | None = None) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    payload = policy or default_export_policy()
    dest.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return dest
