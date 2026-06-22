"""F7 source coverage — snapshot field completeness."""

from __future__ import annotations

from typing import Any


def compute_snapshot_coverage(
    snapshot: dict[str, Any],
    required_fields: list[str] | None,
) -> float:
    """Return % of required snapshot keys present and non-empty."""
    if not required_fields:
        return 100.0
    if not snapshot:
        return 0.0
    present = sum(
        1
        for field in required_fields
        if snapshot.get(field) not in (None, "", [], {})
    )
    return round(100.0 * present / len(required_fields), 2)


def aggregate_source_coverage(entries: list[dict[str, Any]]) -> float:
    """Minimum coverage across decision entries (weakest link)."""
    values: list[float] = []
    for row in entries:
        if row.get("event_type") != "decision":
            continue
        meta = row.get("metadata") or {}
        raw = meta.get("source_coverage_pct")
        if raw is not None:
            values.append(float(raw))
    return min(values) if values else 100.0
