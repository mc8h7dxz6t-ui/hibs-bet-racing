"""Model artifact integrity — deploy-time hash verification."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from inst_spine.errors import IngestValidationError


def compute_artifact_digest(model_snapshot: dict[str, Any]) -> str:
    """Canonical digest excluding artifact_hash field (buyer manifest semantics)."""
    payload = {k: v for k, v in model_snapshot.items() if k != "artifact_hash"}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_artifact_hash(model_snapshot: dict[str, Any]) -> None:
    """Fail-closed when declared artifact_hash does not match canonical digest."""
    declared = str(model_snapshot.get("artifact_hash") or "").strip()
    if not declared.startswith("sha256:"):
        raise IngestValidationError("artifact_hash must be sha256:<hex>")
    expected_hex = compute_artifact_digest(model_snapshot)
    declared_hex = declared.split(":", 1)[1].strip().lower()
    if declared_hex != expected_hex:
        raise IngestValidationError(
            f"artifact_hash mismatch: declared={declared_hex[:16]}… expected=sha256:{expected_hex[:16]}…"
        )


def stamp_artifact_hash(model_snapshot: dict[str, Any]) -> dict[str, Any]:
    """Return snapshot copy with artifact_hash matching canonical digest."""
    out = dict(model_snapshot)
    digest = compute_artifact_digest({**out, "artifact_hash": "pending"})
    out["artifact_hash"] = f"sha256:{digest}"
    return out
