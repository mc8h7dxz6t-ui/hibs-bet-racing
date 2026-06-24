"""Device packet schema contracts — F7 coverage at ingest."""

from __future__ import annotations

from typing import Any

from inst_spine.coverage import compute_snapshot_coverage
from inst_spine.errors import IngestValidationError

# Every packet must carry monotonic device sequence + timestamp.
REQUIRED_PACKET_FIELDS = ["ts", "seq"]

# Buyer profiles — extend without breaking default ward ingest.
DEVICE_PROFILES: dict[str, list[str]] = {
    "rpm_standard": ["hr", "spo2"],
    "vitals_only": ["hr"],
    "minimal": [],
}


def required_fields_for_profile(profile: str) -> list[str]:
    extra = DEVICE_PROFILES.get(profile, DEVICE_PROFILES["rpm_standard"])
    return list(REQUIRED_PACKET_FIELDS) + list(extra)


def validate_packet(pkt: dict[str, Any], *, index: int, profile: str) -> None:
    if not isinstance(pkt, dict):
        raise IngestValidationError(f"packet {index} must be a JSON object")
    required = required_fields_for_profile(profile)
    missing = [f for f in required if pkt.get(f) in (None, "", [], {})]
    if missing:
        raise IngestValidationError(f"packet {index} missing required fields: {missing}")
    seq = pkt.get("seq")
    if seq is not None and not isinstance(seq, int):
        try:
            int(seq)
        except (TypeError, ValueError) as exc:
            raise IngestValidationError(f"packet {index} seq must be integer") from exc


def validate_batch(
    packets: list[dict[str, Any]],
    *,
    profile: str = "rpm_standard",
) -> float:
    """Validate all packets; return aggregate F7 coverage % (weakest packet)."""
    if not packets:
        raise IngestValidationError("packets must be non-empty")
    coverages: list[float] = []
    required = required_fields_for_profile(profile)
    for i, pkt in enumerate(packets):
        validate_packet(pkt, index=i, profile=profile)
        coverages.append(compute_snapshot_coverage(pkt, required))
    return min(coverages) if coverages else 100.0
