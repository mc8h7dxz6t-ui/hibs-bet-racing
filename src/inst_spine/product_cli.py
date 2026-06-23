"""Shared CLI helpers for Inst++ product gold standard."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from inst_spine.check import build_compliance_context, run_institutional_check
from inst_spine.export import build_audit_bundle, verify_audit_bundle, verify_bundle_reproducible
from inst_spine.ledger import AppendOnlyLedger


def run_institutional_export(
    database: Path,
    *,
    product: str,
    out_dir: Path | None = None,
    tarball: Path | None = None,
    repro_check: bool = False,
) -> tuple[int, dict[str, Any]]:
    if repro_check:
        ok, msg = verify_bundle_reproducible(database)
        body = {"ok": ok, "message": msg, "product": product}
        return (0 if ok else 1, body)

    result = build_audit_bundle(
        database,
        out_dir=out_dir,
        tarball_path=tarball,
        product=product,
    )
    body = {
        "ok": result.ok,
        "product": product,
        "bundle_sha256": result.bundle_sha256,
        "tarball": str(result.tarball_path) if result.tarball_path else None,
        "validation": result.validation.message,
        "institutional_passed": result.institutional_passed,
    }
    return (0 if result.ok else 1, body)


def run_institutional_verify(
    tarball: Path,
    *,
    product: str,
    anchor: Path | None = None,
    expected_sha256: str | None = None,
) -> tuple[int, dict[str, Any]]:
    result = verify_audit_bundle(tarball, anchor_path=anchor, expected_sha256=expected_sha256)
    body = {
        "ok": result.ok,
        "product": product,
        "genesis_ok": result.genesis_ok,
        "chain_ok": result.chain_ok,
        "lamport_ok": result.lamport_ok,
        "bundle_sha256_ok": result.bundle_sha256_ok,
        "institutional_passed": result.institutional_passed,
        "message": result.message,
        "details": result.details,
    }
    return (0 if result.ok else 1, body)


def run_f9_check(
    database: Path,
    *,
    observation_lane: bool = False,
    extra_context: dict[str, Any] | None = None,
) -> tuple[int, dict[str, Any]]:
    ledger = AppendOnlyLedger(database)
    ctx = build_compliance_context(ledger, run_f9=True)
    if extra_context:
        ctx.update(extra_context)
    report = run_institutional_check(
        ledger=ledger,
        context=ctx,
        observation_lane=observation_lane,
        run_f9=False,
    )
    return (0 if report.passed else 1, report.to_dict())


def print_json(data: dict[str, Any]) -> None:
    print(json.dumps(data, indent=2))
