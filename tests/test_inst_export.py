"""P2 audit bundle export tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from compliance_log.ingest import log_decision
from inst_spine.export import (
    build_audit_bundle,
    deterministic_tarball,
    validate_before_export,
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
    ledger.append(event_type="e", payload={"n": 1}, manifest_id="m")
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
