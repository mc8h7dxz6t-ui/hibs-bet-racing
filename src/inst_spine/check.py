"""Unified institutional verification orchestrator."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from inst_spine.contracts import InstitutionalCheckReport
from inst_spine.gates.engine import GateEngine
from inst_spine.ledger import AppendOnlyLedger


def run_institutional_check(
    *,
    ledger: AppendOnlyLedger | None = None,
    database: Path | None = None,
    context: dict[str, Any] | None = None,
    observation_lane: bool = False,
) -> InstitutionalCheckReport:
    """
    Single pass/fail institutional check.
    Loads ledger from database if provided; merges optional context for F1–F9.
    """
    ctx = dict(context or {})
    if ledger is None and database is not None:
        ledger = AppendOnlyLedger(database)
    if ledger is not None:
        entries = ledger.list_entries()
        verify = ledger.verify()
        ctx.setdefault("ledger_entries", entries)
        ctx.setdefault("actual_count", len(entries))
        ctx.setdefault("chain_ok", verify.get("chain_ok"))
        ctx.setdefault("lamport_monotonic", verify.get("lamport_monotonic"))

    engine = GateEngine()
    passed, results = engine.all_passed(ctx)

    checks = [{"name": r.gate_id, "passed": r.passed, "detail": r.detail} for r in results]

    if ledger is not None:
        checks.insert(
            0,
            {
                "name": "ledger_chain",
                "passed": bool(ctx.get("chain_ok")),
                "detail": str(ctx.get("chain_ok")),
            },
        )
        checks.insert(
            1,
            {
                "name": "genesis_block",
                "passed": bool(verify.get("genesis_ok")),
                "detail": str(verify.get("genesis_message")),
            },
        )
        checks.insert(
            2,
            {
                "name": "lamport_order",
                "passed": bool(ctx.get("lamport_monotonic")),
                "detail": str(ctx.get("lamport_monotonic")),
            },
        )

    if observation_lane:
        blocking = {"F3", "F4", "ledger_chain", "genesis_block", "lamport_order"}
        passed = all(c["passed"] for c in checks if c["name"] in blocking)
        msg = (
            "Institutional check PASSED (observation lane)."
            if passed
            else "Institutional check FAILED (observation lane)."
        )
    else:
        passed = all(c["passed"] for c in checks)
        msg = "Institutional check PASSED." if passed else "Institutional check FAILED."

    return InstitutionalCheckReport(
        passed=passed,
        checks=checks,
        message=msg,
        extras={"observation_lane": observation_lane},
    )
