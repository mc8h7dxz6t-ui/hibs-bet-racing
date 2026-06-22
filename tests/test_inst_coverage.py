"""F7 coverage and export product identity."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from compliance_log.ingest import log_decision
from inst_spine.check import build_compliance_context
from inst_spine.coverage import compute_snapshot_coverage
from inst_spine.export import build_audit_bundle
from inst_spine.ledger import AppendOnlyLedger


def test_compute_snapshot_coverage_partial():
    pct = compute_snapshot_coverage(
        {"action": "approve", "amount": 100},
        ["action", "amount", "customer_id"],
    )
    assert pct == pytest.approx(66.67, rel=0.01)


def test_f7_fails_on_incomplete_snapshot(tmp_path: Path):
    db = tmp_path / "cov.sqlite"
    log_decision(
        snapshot={"action": "approve"},
        outcome={"ok": True},
        actor="t",
        database=db,
        required_fields=["action", "amount", "customer_id"],
    )
    ledger = AppendOnlyLedger(db)
    ctx = build_compliance_context(ledger, run_f9=False)
    assert ctx["source_coverage_pct"] < 85.0


def test_export_manifest_includes_product(tmp_path: Path):
    db = tmp_path / "prod.sqlite"
    ledger = AppendOnlyLedger(db)
    ledger.append(event_type="decision", payload={"n": 1}, manifest_id="m")
    tar = tmp_path / "b.tar"
    result = build_audit_bundle(
        db,
        out_dir=tmp_path / "out",
        tarball_path=tar,
        product="compliance-logger",
    )
    assert result.ok
    manifest = json.loads((tmp_path / "out" / "MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["product"] == "compliance-logger"
