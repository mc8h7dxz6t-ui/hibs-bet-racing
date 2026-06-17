"""Async poll worker — one feed per deployment."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from altdata.ladders import FIELD_LADDERS
from altdata.resolver import FieldResolver
from inst_spine.contracts import RunManifest, stable_id
from inst_spine.ledger import AppendOnlyLedger


@dataclass
class PollResult:
    ok: bool
    feed_id: str
    record: dict[str, Any]
    coverage_pct: float
    manifest_id: str
    rescue_rate_pct: float


def poll_once(
    *,
    feed_id: str,
    ctx: dict[str, Any],
    fields: list[str] | None = None,
    database: Path | None = None,
) -> PollResult:
    """Single poll cycle — resolve fields, snapshot to ledger."""
    fields = fields or list(FIELD_LADDERS.keys())
    resolver = FieldResolver()
    record = resolver.resolve_record(fields, ctx)
    coverage = resolver.coverage_pct(record, fields)
    meta = record.get("_meta") or {}
    rescue_fields = meta.get("rescue_fields") or []
    rescue_rate = (100.0 * len(rescue_fields) / len(fields)) if fields else 0.0

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    manifest = RunManifest(
        manifest_id=stable_id(feed_id, now),
        run_kind="altdata_poll",
        config_hash=stable_id(feed_id, "v1"),
        writer_id=feed_id,
        created_at=now,
        extras={"coverage_pct": coverage, "rescue_rate_pct": rescue_rate},
    )

    db = database or Path(f"data/altdata_{feed_id}.sqlite")
    ledger = AppendOnlyLedger(db, writer_id=feed_id)
    ledger.append(
        event_type="snapshot",
        payload={"feed_id": feed_id, "record": record},
        manifest_id=manifest.manifest_id,
        metadata={"manifest_hash": manifest.manifest_hash, "coverage_pct": coverage},
    )

    ok = coverage >= 85.0
    return PollResult(
        ok=ok,
        feed_id=feed_id,
        record=record,
        coverage_pct=coverage,
        manifest_id=manifest.manifest_id,
        rescue_rate_pct=rescue_rate,
    )
