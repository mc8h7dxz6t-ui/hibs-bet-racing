"""P2 audit bundle export tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from compliance_log.ingest import log_decision
from inst_spine.check import build_compliance_context, run_institutional_check
from inst_spine.export import (
    build_audit_bundle,
    deterministic_tarball,
    validate_before_export,
    verify_audit_bundle,
    verify_bundle_reproducible,
)
from inst_spine.ledger import AppendOnlyLedger


def test_export_aborts_on_empty_chain(tmp_path: Path):
    db = tmp_path / "empty.sqlite"
    # No ledger init — can't easily get empty without genesis since AppendOnlyLedger always creates genesis
    ledger = AppendOnlyLedger(db)
    v = validate_before_export(ledger=ledger)
    assert v.ok


def test_p2_bundle_with_entries(tmp_path: Path):
    db = tmp_path / "compliance.sqlite"
    log_decision(
        snapshot={"action": "approve"},
        outcome={"ok": True},
        actor="auditor",
        database=db,
    )
    out = tmp_path / "bundle"
    tar = tmp_path / "bundle.tar"
    result = build_audit_bundle(db, out_dir=out, tarball_path=tar)
    assert result.ok
    assert result.bundle_sha256
    assert tar.exists()
    assert tar.with_suffix(".tar.sha256").exists()
    assert (out / "MANIFEST.json").exists()


def test_f9_reproducible_tarball(tmp_path: Path):
    db = tmp_path / "repro.sqlite"
    ledger = AppendOnlyLedger(db)
    ledger.append(event_type="decision", payload={"n": 1}, manifest_id="m")
    ok, digest = verify_bundle_reproducible(db, runs=2)
    assert ok
    assert len(digest) == 64


def test_export_fails_tampered_genesis(tmp_path: Path):
    db = tmp_path / "tamper.sqlite"
    ledger = AppendOnlyLedger(db)
    ledger.append(event_type="e", payload={"x": 1}, manifest_id="m")
    anchor = ledger.anchor_path
    anchor.write_text('{"instance_uuid":"fake","genesis_hash":"dead"}', encoding="utf-8")
    v = validate_before_export(ledger=ledger)
    assert not v.ok


def test_deterministic_tar_sorted(tmp_path: Path):
    d = tmp_path / "tarsrc"
    d.mkdir()
    (d / "b.txt").write_text("b", encoding="utf-8")
    (d / "a.txt").write_text("a", encoding="utf-8")
    t1 = deterministic_tarball(d)
    t2 = deterministic_tarball(d)
    assert t1 == t2


def test_offline_verify_audit_bundle(tmp_path: Path):
    db = tmp_path / "compliance.sqlite"
    log_decision(
        snapshot={"action": "approve"},
        outcome={"ok": True},
        actor="auditor",
        database=db,
    )
    tar = tmp_path / "bundle.tar"
    result = build_audit_bundle(db, out_dir=tmp_path / "bundle", tarball_path=tar)
    assert result.ok

    offline = verify_audit_bundle(tar)
    assert offline.ok
    assert offline.chain_ok
    assert offline.genesis_ok
    assert offline.lamport_ok
    assert offline.bundle_sha256_ok
    assert offline.institutional_passed


def test_export_aborts_on_institutional_fail(tmp_path: Path):
    db = tmp_path / "genesis_only.sqlite"
    AppendOnlyLedger(db)
    result = build_audit_bundle(db, out_dir=tmp_path / "out", tarball_path=tmp_path / "out.tar")
    assert not result.ok
    assert not result.institutional_passed
    assert result.tarball_path is None


def test_build_compliance_context_f9(tmp_path: Path):
    db = tmp_path / "f9.sqlite"
    ledger = AppendOnlyLedger(db)
    ledger.append(event_type="decision", payload={"n": 1}, manifest_id="m1")
    ctx = build_compliance_context(ledger, run_f9=True)
    assert ctx.get("export_hash_a")
    assert ctx["export_hash_a"] == ctx["export_hash_b"]
    report = run_institutional_check(ledger=ledger, context=ctx, run_f9=False)
    f9 = next(c for c in report.checks if c["name"] == "F9")
    assert f9["passed"]
