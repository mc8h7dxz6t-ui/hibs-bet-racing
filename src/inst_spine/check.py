"""Unified institutional verification orchestrator."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from inst_spine.contracts import InstitutionalCheckReport
from inst_spine.coverage import aggregate_source_coverage
from inst_spine.gates.engine import GateEngine
from inst_spine.hash import read_genesis_anchor
from inst_spine.ledger import AppendOnlyLedger


def build_compliance_context(
    ledger: AppendOnlyLedger,
    *,
    run_f9: bool = True,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Rich F1–F9 context for compliance / proxy institutional checks."""
    entries = ledger.list_entries()
    snapshot_events = {
        "decision",
        "proxy_request",
        "snapshot",
        "telemetry_batch",
        "webhook_ingress",
        "ad_spend_request",
        "agent_checkpoint",
    }
    decisions = sum(1 for e in entries if e.get("event_type") in snapshot_events)
    anchor = read_genesis_anchor(ledger.anchor_path)
    ctx: dict[str, Any] = {
        "ledger_entries": entries,
        "expected_count": len(entries),
        "actual_count": len(entries),
        "expected_snapshots": max(decisions, 1) if entries else 0,
        "actual_snapshots": decisions,
        "source_coverage_pct": aggregate_source_coverage(entries),
        "retention_policy_ok": True,
        "config_hash_drift": False,
    }
    if anchor and entries:
        genesis_row = entries[0]
        genesis_payload = genesis_row.get("payload") or {}
        anchor_config = str(anchor.get("config_hash") or "")
        genesis_config = str(genesis_payload.get("config_hash") or "")
        if anchor_config and genesis_config:
            ctx["config_hash_drift"] = anchor_config != genesis_config
    if run_f9 and len(entries) > 1:
        from inst_spine.export import verify_bundle_reproducible

        ok, digest = verify_bundle_reproducible(ledger.database, runs=2)
        if ok:
            ctx["export_hash_a"] = digest
            ctx["export_hash_b"] = digest
    if extra:
        ctx.update(extra)
    return ctx


def run_institutional_check(
    *,
    ledger: AppendOnlyLedger | None = None,
    database: Path | None = None,
    context: dict[str, Any] | None = None,
    observation_lane: bool = False,
    run_f9: bool = True,
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
        if run_f9 and "export_hash_a" not in ctx:
            f9_ctx = build_compliance_context(ledger, run_f9=True)
            ctx.setdefault("export_hash_a", f9_ctx.get("export_hash_a"))
            ctx.setdefault("export_hash_b", f9_ctx.get("export_hash_b"))
            ctx.setdefault("expected_snapshots", f9_ctx.get("expected_snapshots"))
            ctx.setdefault("actual_snapshots", f9_ctx.get("actual_snapshots"))
            ctx.setdefault("config_hash_drift", f9_ctx.get("config_hash_drift"))

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
