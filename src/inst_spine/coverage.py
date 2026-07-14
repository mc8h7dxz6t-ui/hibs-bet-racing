"""F7 source coverage — snapshot field completeness."""

from __future__ import annotations

from typing import Any

_COVERAGE_EVENT_TYPES = frozenset(
    {
        "decision",
        "snapshot",
        "telemetry_batch",
        "model_governance",
        "agent_checkpoint",
    }
)

_METADATA_COVERAGE_KEYS = ("source_coverage_pct", "coverage_pct")


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


def _coverage_from_row(row: dict[str, Any]) -> float | None:
    if row.get("event_type") not in _COVERAGE_EVENT_TYPES:
        return None
    meta = row.get("metadata") or {}
    for key in _METADATA_COVERAGE_KEYS:
        raw = meta.get(key)
        if raw is not None:
            return float(raw)
    payload = row.get("payload") or {}
    if row.get("event_type") == "snapshot" and "coverage_pct" in payload:
        return float(payload["coverage_pct"])
    return None


def aggregate_source_coverage(entries: list[dict[str, Any]]) -> float:
    """Minimum coverage across snapshot-bearing entries (weakest link)."""
    values: list[float] = []
    for row in entries:
        pct = _coverage_from_row(row)
        if pct is not None:
            values.append(pct)
    return min(values) if values else 100.0
