"""Record model governance events into the institutional hash chain."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from inst_spine.contracts import RunManifest, stable_id
from inst_spine.coverage import compute_snapshot_coverage
from inst_spine.errors import IngestValidationError
from inst_spine.ledger import AppendOnlyLedger
from model_governor.lifecycle import validate_deploy_drift_gate, validate_lifecycle_transition
from model_governor.integrity import validate_artifact_hash

GOVERNANCE_ACTIONS = frozenset(
    {"register", "approve", "reject", "deploy", "retire", "drift_alert"}
)

REQUIRED_MODEL_FIELDS = ["model_id", "version", "artifact_hash", "risk_tier"]


def _default_db() -> Path:
    return Path("data/model_governor.sqlite")


def manifest_from_dict(data: dict[str, Any]) -> RunManifest:
    if "manifest_id" not in data:
        raise IngestValidationError("manifest_id is required in RunManifest JSON")
    return RunManifest(
        manifest_id=str(data["manifest_id"]),
        run_kind=str(data.get("run_kind") or "model_governance"),
        config_hash=str(data.get("config_hash") or stable_id("model-governor", "config", "v1")),
        writer_id=str(data.get("writer_id") or "model-governor"),
        created_at=str(data.get("created_at") or ""),
        extras=dict(data.get("extras") or {}),
    )


def record_governance_event(
    *,
    action: str,
    model_snapshot: dict[str, Any],
    outcome: dict[str, Any] | None = None,
    actor: str = "model-governor",
    manifest: RunManifest | None = None,
    database: Path | None = None,
) -> dict[str, Any]:
    """Append one model governance event (register, approve, deploy, etc.)."""
    act = (action or "").strip().lower()
    if act not in GOVERNANCE_ACTIONS:
        raise IngestValidationError(
            f"action must be one of {sorted(GOVERNANCE_ACTIONS)}; got {action!r}"
        )
    if not isinstance(model_snapshot, dict):
        raise IngestValidationError("model_snapshot must be a JSON object")

    missing = [f for f in REQUIRED_MODEL_FIELDS if not model_snapshot.get(f)]
    if missing:
        raise IngestValidationError(f"model_snapshot missing required fields: {missing}")

    validate_artifact_hash(model_snapshot)

    db = database or _default_db()
    validate_lifecycle_transition(
        action=act,
        model_id=str(model_snapshot["model_id"]),
        version=str(model_snapshot["version"]),
        database=db,
    )

    if act == "deploy":
        import os
        from pathlib import Path as _Path

        baseline = os.environ.get("MODEL_GOVERNOR_DRIFT_BASELINE", "").strip()
        deploy_features = model_snapshot.get("deploy_features")
        if baseline and isinstance(deploy_features, dict):
            try:
                features = {k: float(v) for k, v in deploy_features.items()}
            except (TypeError, ValueError) as exc:
                raise IngestValidationError("deploy_features must be numeric") from exc
            mode = os.environ.get("MODEL_GOVERNOR_DRIFT_MODE", "shadow").strip()
            validate_deploy_drift_gate(
                model_id=str(model_snapshot["model_id"]),
                version=str(model_snapshot["version"]),
                features=features,
                baseline_path=_Path(baseline),
                mode=mode,
                database=db,
            )

    out = outcome if outcome is not None else {}
    if not isinstance(out, dict):
        raise IngestValidationError("outcome must be a JSON object")

    db = database or _default_db()
    ledger = AppendOnlyLedger(db, writer_id=actor)
    coverage_pct = compute_snapshot_coverage(model_snapshot, REQUIRED_MODEL_FIELDS)
    model_id = str(model_snapshot["model_id"])
    version = str(model_snapshot["version"])
    manifest_id = (
        manifest.manifest_id
        if manifest
        else stable_id(model_id, version, act, actor)
    )

    entry = ledger.append(
        event_type="model_governance",
        payload={
            "action": act,
            "actor": actor,
            "model_snapshot": model_snapshot,
            "outcome": out,
        },
        manifest_id=manifest_id,
        metadata={
            "manifest_hash": manifest.manifest_hash if manifest else None,
            "model_id": model_id,
            "model_version": version,
            "governance_action": act,
            "source_coverage_pct": coverage_pct,
            "required_fields": REQUIRED_MODEL_FIELDS,
        },
    )
    return entry.to_dict()
