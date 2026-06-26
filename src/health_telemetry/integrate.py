"""Drop-in gateway hook — schema + sequence gate + ledger append."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from health_telemetry.ingest import ingest_batch


def ingest_device_batch(
    *,
    device_id: str,
    packets: list[dict[str, Any]],
    ledger_db: Path,
    profile: str = "rpm_standard",
    actor: str = "health-gateway",
    skip_sequence_gate: bool = False,
) -> dict[str, Any]:
    """
    Call from your RPM gateway before acknowledging device upload:

        result = ingest_device_batch(
            device_id=device["id"],
            packets=normalized_packets,
            ledger_db=Path("data/health_telemetry.sqlite"),
        )
        if not result.get("entry_id"):
            raise GatewayReject(...)
    """
    return ingest_batch(
        device_id=device_id,
        packets=packets,
        database=ledger_db,
        profile=profile,
        actor=actor,
        skip_sequence_gate=skip_sequence_gate,
    )
