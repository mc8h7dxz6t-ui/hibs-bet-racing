"""Health Telemetry Recorder — batch ingest on institutional spine."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from inst_spine.clocks import utc_now_iso
from inst_spine.contracts import RunManifest, stable_id
from inst_spine.errors import IngestValidationError
from inst_spine.ledger import AppendOnlyLedger


def ingest_batch(
    *,
    device_id: str,
    packets: list[dict[str, Any]],
    actor: str = "health-gateway",
    database: Path | None = None,
) -> dict[str, Any]:
    """Append a batch of sensor readings as one tamper-evident chain entry."""
    if not device_id:
        raise IngestValidationError("device_id is required")
    if not packets:
        raise IngestValidationError("packets must be non-empty")
    for i, pkt in enumerate(packets):
        if not isinstance(pkt, dict):
            raise IngestValidationError(f"packet {i} must be a JSON object")

    db = database or Path("data/health_telemetry.sqlite")
    ledger = AppendOnlyLedger(db, writer_id=actor)
    manifest = RunManifest(
        manifest_id=stable_id(device_id, "batch", str(len(packets))),
        run_kind="health_telemetry",
        config_hash=stable_id(device_id, "config", "v1"),
        writer_id=actor,
        created_at=utc_now_iso(),
        extras={"device_id": device_id, "packet_count": len(packets)},
    )
    entry = ledger.append(
        event_type="telemetry_batch",
        payload={"device_id": device_id, "packets": packets, "count": len(packets)},
        manifest_id=manifest.manifest_id,
        metadata={"manifest_hash": manifest.manifest_hash, "packet_count": len(packets)},
    )
    return entry.to_dict()
