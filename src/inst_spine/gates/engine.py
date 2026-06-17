"""Staged gate engine — F1–F9 evidence matrix."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

GateFn = Callable[[dict[str, Any]], tuple[bool, str]]


@dataclass(frozen=True)
class GateResult:
    gate_id: str
    passed: bool
    detail: str


class GateEngine:
    """Run F1–F9 or custom gate checklist."""

    def __init__(self, gates: dict[str, GateFn] | None = None) -> None:
        self.gates = gates or build_f_gates()

    def run(self, context: dict[str, Any]) -> list[GateResult]:
        return [
            GateResult(gate_id=gid, passed=ok, detail=detail)
            for gid, fn in self.gates.items()
            for ok, detail in [fn(context)]
        ]

    def all_passed(self, context: dict[str, Any]) -> tuple[bool, list[GateResult]]:
        results = self.run(context)
        return all(r.passed for r in results), results


def build_f_gates() -> dict[str, GateFn]:
    return {
        "F1": _f1_snapshot_completeness,
        "F2": _f2_manifest_linkage,
        "F3": _f3_hash_chain,
        "F4": _f4_lamport_monotonic,
        "F5": _f5_config_drift,
        "F6": _f6_reconciliation,
        "F7": _f7_source_coverage,
        "F8": _f8_retention_policy,
        "F9": _f9_export_reproducibility,
    }


def _f1_snapshot_completeness(ctx: dict[str, Any]) -> tuple[bool, str]:
    expected = int(ctx.get("expected_snapshots") or 0)
    actual = int(ctx.get("actual_snapshots") or 0)
    if expected <= 0:
        return True, "no snapshots required"
    ok = actual >= expected
    return ok, f"snapshots {actual}/{expected}"


def _f2_manifest_linkage(ctx: dict[str, Any]) -> tuple[bool, str]:
    entries = ctx.get("ledger_entries") or []
    missing = sum(
        1
        for e in entries
        if e.get("event_type") != "genesis" and not e.get("manifest_id")
    )
    ok = missing == 0 if entries else True
    return ok, f"manifest missing on {missing} entries"


def _f3_hash_chain(ctx: dict[str, Any]) -> tuple[bool, str]:
    from inst_spine.hash import verify_chain

    entries = ctx.get("ledger_entries") or []
    if not entries:
        return True, "empty ledger"
    result = verify_chain(entries)
    return result.ok, result.message


def _f4_lamport_monotonic(ctx: dict[str, Any]) -> tuple[bool, str]:
    from inst_spine.hash import verify_lamport_monotonic

    entries = ctx.get("ledger_entries") or []
    if not entries:
        return True, "empty ledger"
    ok = verify_lamport_monotonic(entries)
    return ok, "lamport strictly increasing" if ok else "lamport violation detected"


def _f5_config_drift(ctx: dict[str, Any]) -> tuple[bool, str]:
    drift = bool(ctx.get("config_hash_drift"))
    return (not drift), "config stable" if not drift else "config hash drift"


def _f6_reconciliation(ctx: dict[str, Any]) -> tuple[bool, str]:
    expected = ctx.get("expected_count")
    actual = ctx.get("actual_count")
    if expected is None or actual is None:
        return True, "recon not required"
    ok = int(expected) == int(actual)
    return ok, f"expected={expected} actual={actual}"


def _f7_source_coverage(ctx: dict[str, Any]) -> tuple[bool, str]:
    pct = float(ctx.get("source_coverage_pct") or 100.0)
    floor = float(ctx.get("min_source_coverage_pct") or 85.0)
    ok = pct >= floor
    return ok, f"coverage {pct:.1f}% (min {floor:.1f}%)"


def _f8_retention_policy(ctx: dict[str, Any]) -> tuple[bool, str]:
    ok = bool(ctx.get("retention_policy_ok", True))
    return ok, "retention policy ok" if ok else "retention policy violation"


def _f9_export_reproducibility(ctx: dict[str, Any]) -> tuple[bool, str]:
    a = ctx.get("export_hash_a")
    b = ctx.get("export_hash_b")
    if not a or not b:
        return True, "export repro not tested"
    ok = str(a) == str(b)
    return ok, "export hashes match" if ok else "export hashes differ"
