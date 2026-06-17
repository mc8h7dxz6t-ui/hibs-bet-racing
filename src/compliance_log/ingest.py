"""Ingest business decisions into Inst++ hash chain."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from inst_spine.contracts import RunManifest, stable_id
from inst_spine.ledger import AppendOnlyLedger


def _default_db() -> Path:
    return Path("data/compliance_ledger.sqlite")


def log_decision(
    *,
    snapshot: dict[str, Any],
    outcome: dict[str, Any],
    actor: str,
    manifest: RunManifest | None = None,
    database: Path | None = None,
    async_writes: bool = False,
) -> dict[str, Any]:
    """
    Record one decision with input snapshot and outcome.
    Returns ledger entry dict.
    """
    db = database or _default_db()
    writer = actor or "compliance"
    ledger = AppendOnlyLedger(db, writer_id=writer, async_writes=async_writes)
    if async_writes:
        ledger.start_async_writer()

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
        metadata={"manifest_hash": manifest.manifest_hash if manifest else None},
    )
    if async_writes:
        ledger.flush()

    return entry.to_dict()
