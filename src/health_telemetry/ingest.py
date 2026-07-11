"""Health Telemetry Recorder — batch ingest on institutional spine."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from health_telemetry.schema import validate_batch
from health_telemetry.sequence import DeviceSequenceStore
from inst_spine.clocks import utc_now_iso
from inst_spine.contracts import RunManifest, stable_id
from inst_spine.errors import IngestValidationError
from inst_spine.ledger_registry import get_ledger


def _packet_seqs(packets: list[dict[str, Any]]) -> list[int]:
    seqs: list[int] = []
    for i, pkt in enumerate(packets):
        raw = pkt.get("seq")
        if raw is None:
            raise IngestValidationError(f"packet {i} missing seq for sequence gate")
        seqs.append(int(raw))
    return seqs


def _packet_summaries(packets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """PHI-light summaries for observation-lane export."""
    out: list[dict[str, Any]] = []
    for pkt in packets:
        canonical = json.dumps(pkt, sort_keys=True, separators=(",", ":"))
        out.append(
            {
                "seq": pkt.get("seq"),
                "ts": pkt.get("ts"),
                "packet_sha256": hashlib.sha256(canonical.encode()).hexdigest(),
                "fields": sorted(k for k in pkt if k not in ("seq", "ts")),
            }
        )
    return out


def ingest_batch(
    *,
    device_id: str,
    packets: list[dict[str, Any]],
    actor: str = "health-gateway",
    database: Path | None = None,
    profile: str = "rpm_standard",
    skip_sequence_gate: bool = False,
    sequence_db: Path | None = None,
) -> dict[str, Any]:
    """
    Append a batch of sensor readings as one tamper-evident chain entry.

    Pipeline: schema validate → per-device sequence gate → ledger append with F7 metadata.
    """
    if not device_id:
        raise IngestValidationError("device_id is required")

    coverage_pct = validate_batch(packets, profile=profile)

    seq_meta: dict[str, Any] = {"sequence_gate": "skipped"}
    if not skip_sequence_gate:
        store = (
            DeviceSequenceStore(sequence_db)
            if sequence_db
            else DeviceSequenceStore.for_ledger(database or Path("data/health_telemetry.sqlite"))
        )
        seq_meta = store.validate_and_commit(device_id, _packet_seqs(packets))
        seq_meta["sequence_gate"] = "passed"

    db = database or Path("data/health_telemetry.sqlite")
    ledger = get_ledger(db, writer_id=actor)
    manifest = RunManifest(
        manifest_id=stable_id(device_id, "batch", str(packets[0].get("seq")), str(len(packets))),
        run_kind="health_telemetry",
        config_hash=stable_id(device_id, "profile", profile),
        writer_id=actor,
        created_at=utc_now_iso(),
        extras={
            "device_id": device_id,
            "packet_count": len(packets),
            "profile": profile,
            "coverage_pct": coverage_pct,
            **{k: v for k, v in seq_meta.items() if k != "sequence_gate"},
        },
    )
    entry = ledger.append(
        event_type="telemetry_batch",
        payload={
            "device_id": device_id,
            "profile": profile,
            "packets": packets,
            "packet_summaries": _packet_summaries(packets),
            "count": len(packets),
        },
        manifest_id=manifest.manifest_id,
        metadata={
            "manifest_hash": manifest.manifest_hash,
            "packet_count": len(packets),
            "source_coverage_pct": coverage_pct,
            "coverage_pct": coverage_pct,
            "device_id": device_id,
            "sequence_gate": seq_meta.get("sequence_gate", "passed"),
            "last_seq": seq_meta.get("last_seq"),
        },
    )
    result = entry.to_dict()
    result["coverage_pct"] = coverage_pct
    result["sequence"] = seq_meta
    return result
