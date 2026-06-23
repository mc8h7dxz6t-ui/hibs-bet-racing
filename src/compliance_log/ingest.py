"""Ingest business decisions into Inst++ hash chain."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from inst_spine.contracts import RunManifest, stable_id
from inst_spine.coverage import compute_snapshot_coverage
from inst_spine.errors import IngestValidationError
from inst_spine.ledger import AppendOnlyLedger


def _default_db() -> Path:
    return Path("data/compliance_ledger.sqlite")


def manifest_from_dict(data: dict[str, Any]) -> RunManifest:
    """Build RunManifest from JSON file or CLI payload."""
    if "manifest_id" not in data:
        raise IngestValidationError("manifest_id is required in RunManifest JSON")
    return RunManifest(
        manifest_id=str(data["manifest_id"]),
        run_kind=str(data.get("run_kind") or "compliance"),
        config_hash=str(data.get("config_hash") or stable_id("compliance", "config", "v1")),
        writer_id=str(data.get("writer_id") or "compliance"),
        created_at=str(data.get("created_at") or ""),
        extras=dict(data.get("extras") or {}),
    )


def log_decision(
    *,
    snapshot: dict[str, Any],
    outcome: dict[str, Any],
    actor: str,
    manifest: RunManifest | None = None,
    database: Path | None = None,
    async_writes: bool = False,
    required_fields: list[str] | None = None,
) -> dict[str, Any]:
    """
    Record one decision with input snapshot and outcome.
    Returns ledger entry dict.
    """
    if not isinstance(snapshot, dict):
        raise IngestValidationError("snapshot must be a JSON object")
    if not isinstance(outcome, dict):
        raise IngestValidationError("outcome must be a JSON object")

    db = database or _default_db()
    writer = actor or "compliance"
    ledger = AppendOnlyLedger(db, writer_id=writer, async_writes=async_writes)
    if async_writes:
        ledger.start_async_writer()

    fields = required_fields
    if fields is None and manifest is not None:
        raw = manifest.extras.get("required_snapshot_fields")
        if isinstance(raw, list):
            fields = [str(x) for x in raw]

    coverage_pct = compute_snapshot_coverage(snapshot, fields)

    payload = {
        "actor": actor,
        "snapshot": snapshot,
        "outcome": outcome,
    }
    manifest_id = manifest.manifest_id if manifest else stable_id(actor, "decision", str(len(snapshot)))

    entry = ledger.append(
        event_type="decision",
        payload=payload,
        manifest_id=manifest_id,
        metadata={
            "manifest_hash": manifest.manifest_hash if manifest else None,
            "source_coverage_pct": coverage_pct,
            "required_fields": fields or [],
        },
    )
    if async_writes:
        ledger.flush()

    return entry.to_dict()
