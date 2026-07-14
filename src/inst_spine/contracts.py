"""Domain-agnostic Inst++ contracts — zero sports imports."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
from typing import Any


def canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))


@dataclass(frozen=True)
class RunManifest:
    """Immutable run identity for any batch or request session."""

    manifest_id: str
    run_kind: str
    config_hash: str
    writer_id: str
    created_at: str
    extras: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def manifest_hash(self) -> str:
        return hashlib.sha256(canonical_json(self.to_dict()).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ApiIntent:
    """Untrusted outbound API request from a client automation."""

    intent_id: str
    client_id: str
    method: str
    path: str
    payload_hash: str
    reference_price: float | None = None
    stake_units: float | None = None


@dataclass(frozen=True)
class LedgerEntry:
    """Single append-only ledger row with chained hash."""

    entry_id: str
    event_type: str
    writer_id: str
    lamport_seq: int
    wall_time_utc: str
    manifest_id: str | None
    payload: dict[str, Any]
    prev_hash: str
    entry_hash: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GateFailure:
    gate_id: str
    detail: str


@dataclass(frozen=True)
class InstitutionalCheckReport:
    passed: bool
    checks: list[dict[str, Any]]
    message: str
    extras: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "checks": self.checks,
            "message": self.message,
            "extras": self.extras,
        }


def stable_id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:32]
