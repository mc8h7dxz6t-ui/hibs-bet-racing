"""Compliance log CLI."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from compliance_log.ingest import log_decision, manifest_from_dict
from inst_spine.check import build_compliance_context, run_institutional_check
from inst_spine.cli_util import run_cli
from inst_spine.errors import IngestValidationError
from inst_spine.ledger_factory import open_ledger

PRODUCT = "compliance-logger"


def _load_json(path_or_raw: str) -> dict:
    p = Path(path_or_raw)
    if p.is_file():
        return json.loads(p.read_text(encoding="utf-8"))
    return json.loads(path_or_raw)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="compliance-log")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ingest = sub.add_parser("ingest", help="Log a decision from JSON snapshot file")
    p_ingest.add_argument("--snapshot", required=True, help="Path to snapshot JSON")
    p_ingest.add_argument("--outcome", default="{}", help="Outcome JSON string or path")
    p_ingest.add_argument("--actor", default="system")
    p_ingest.add_argument("--manifest", type=Path, default=None, help="RunManifest JSON file")
    p_ingest.add_argument("--database", type=Path, default=Path("data/compliance_ledger.sqlite"))

    p_check = sub.add_parser("check", help="Run F1–F9 institutional check")
    p_check.add_argument("--database", type=Path, default=Path("data/compliance_ledger.sqlite"))
    p_check.add_argument("--observation-lane", action="store_true")

    p_verify = sub.add_parser("verify-chain", help="Verify hash chain only")
    p_verify.add_argument("--database", type=Path, default=Path("data/compliance_ledger.sqlite"))

    p_export = sub.add_parser("export", help="P2 deterministic audit bundle (tar + sha256)")
    p_export.add_argument("--database", type=Path, default=Path("data/compliance_ledger.sqlite"))
    p_export.add_argument("--out-dir", type=Path, default=None)
    p_export.add_argument("--tarball", type=Path, default=None)
    p_export.add_argument("--anchor", type=Path, default=None, help="Offsite genesis anchor JSON")
    p_export.add_argument("--repro-check", action="store_true", help="F9 reproducibility test")

    p_bundle = sub.add_parser("verify-bundle", help="Offline auditor dry-run on exported tarball")
    p_bundle.add_argument("--tarball", type=Path, required=True)
    p_bundle.add_argument("--anchor", type=Path, default=None, help="Offsite genesis anchor JSON")
    p_bundle.add_argument("--sha256", default=None, help="Expected bundle SHA256 hex")

    args = parser.parse_args(argv)

    if args.cmd == "ingest":
        snap = _load_json(args.snapshot)
        if not isinstance(snap, dict):
            raise IngestValidationError("--snapshot must be a JSON object")
        outcome = _load_json(args.outcome)
        manifest = None
        if args.manifest is not None:
            manifest = manifest_from_dict(
                json.loads(Path(args.manifest).read_text(encoding="utf-8"))
            )
        entry = log_decision(
            snapshot=snap,
            outcome=outcome,
            actor=args.actor,
            manifest=manifest,
            database=args.database,
        )
        print(json.dumps(entry, indent=2))
        return 0

    if args.cmd == "check":
        ledger = open_ledger(args.database)
        ctx = build_compliance_context(ledger, run_f9=True)
        report = run_institutional_check(
            ledger=ledger,
            context=ctx,
            observation_lane=args.observation_lane,
            run_f9=False,
        )
        print(json.dumps(report.to_dict(), indent=2))
        return 0 if report.passed else 1

    if args.cmd == "verify-chain":
        ledger = open_ledger(args.database)
        print(json.dumps(ledger.verify(), indent=2))
        return 0

    if args.cmd == "export":
        from compliance_log.export_policy import write_policy_file
        from inst_spine.export import build_audit_bundle, verify_bundle_reproducible

        if args.repro_check:
            ok, msg = verify_bundle_reproducible(args.database)
            print(json.dumps({"ok": ok, "message": msg, "product": PRODUCT}, indent=2))
            return 0 if ok else 1
        policy_path = Path(args.database).parent / "export_policy.json"
        write_policy_file(policy_path)
        result = build_audit_bundle(
            args.database,
            out_dir=args.out_dir,
            tarball_path=args.tarball,
            anchor_path=args.anchor,
            product=PRODUCT,
            extra_files={"export_policy.json": policy_path},
            observation_lane=os.getenv("INST_COMPLIANCE_OBSERVATION_LANE", "0") == "1",
        )
        print(
            json.dumps(
                {
                    "ok": result.ok,
                    "product": PRODUCT,
                    "bundle_sha256": result.bundle_sha256,
                    "tarball": str(result.tarball_path) if result.tarball_path else None,
                    "validation": result.validation.message,
                    "institutional_passed": result.institutional_passed,
                },
                indent=2,
            )
        )
        return 0 if result.ok else 1

    if args.cmd == "verify-bundle":
        from inst_spine.export import verify_audit_bundle

        result = verify_audit_bundle(
            args.tarball,
            anchor_path=args.anchor,
            expected_sha256=args.sha256,
        )
        print(
            json.dumps(
                {
                    "ok": result.ok,
                    "product": PRODUCT,
                    "genesis_ok": result.genesis_ok,
                    "chain_ok": result.chain_ok,
                    "lamport_ok": result.lamport_ok,
                    "bundle_sha256_ok": result.bundle_sha256_ok,
                    "institutional_passed": result.institutional_passed,
                    "message": result.message,
                    "details": result.details,
                },
                indent=2,
            )
        )
        return 0 if result.ok else 1

    return 1


if __name__ == "__main__":
    run_cli(lambda: main())
