"""Institutional contracts — racing domain, trading_core-compatible boundaries."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
from typing import Any


@dataclass(frozen=True)
class RunManifest:
    """Immutable run identity for refresh / score / backtest replay."""

    manifest_id: str
    run_kind: str  # refresh | snapshot_backfill | gate_benchmark | paper_settle
    card_date: str | None
    config_hash: str
    model_version: str
    scoring_method: str | None
    git_sha: str | None
    odds_source: str | None
    runner_count: int
    value_flag_count: int
    created_at: str
    extras: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        base = asdict(self)
        return base

    def canonical_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, default=str)

    @property
    def manifest_hash(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class BetIntent:
    """Untrusted bet target from strategy layer (paper or live shadow)."""

    intent_msg_id: str
    strategy_id: str
    venue: str  # paper | matchbook | shadow
    runner_id: str
    race_id: str
    bet_type: str  # each_way | win | place
    stake_units: str
    offered_win: str
    model_ev: str | None
    timestamp_ns: int


@dataclass(frozen=True)
class LedgerEvent:
    """Append-only ledger event — auditable, never mutated."""

    event_id: str
    event_type: str  # bet_placed | bet_settled | manifest_written | recon_pass | recon_fail
    runner_id: str | None
    race_id: str | None
    payload_json: str
    manifest_id: str | None
    verification_hash: str | None
    created_at: str


@dataclass(frozen=True)
class ReconDiscrepancy:
    status: str
    field: str
    runner_id: str | None = None
    internal_value: str = ""
    derived_value: str = ""


@dataclass(frozen=True)
class PaperReconciliationResult:
    is_clean: bool
    manifest_id: str | None
    card_date: str | None
    expected_value_picks: int
    ledger_value_picks: int
    missing_in_ledger: list[str]
    extra_in_ledger: list[str]
    field_mismatches: list[ReconDiscrepancy]
    discrepancies: list[ReconDiscrepancy]

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_clean": self.is_clean,
            "manifest_id": self.manifest_id,
            "card_date": self.card_date,
            "expected_value_picks": self.expected_value_picks,
            "ledger_value_picks": self.ledger_value_picks,
            "missing_in_ledger": self.missing_in_ledger,
            "extra_in_ledger": self.extra_in_ledger,
            "field_mismatches": [asdict(d) for d in self.field_mismatches],
            "discrepancies": [asdict(d) for d in self.discrepancies],
        }


def stable_event_id(*parts: str) -> str:
    payload = "|".join(parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]
