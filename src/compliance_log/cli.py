"""Compliance log CLI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from compliance_log.ingest import log_decision
from inst_spine.check import run_institutional_check
from inst_spine.ledger import AppendOnlyLedger


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="compliance-log")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ingest = sub.add_parser("ingest", help="Log a decision from JSON snapshot file")
    p_ingest.add_argument("--snapshot", required=True, help="Path to snapshot JSON")
    p_ingest.add_argument("--outcome", default="{}", help="Outcome JSON string or path")
    p_ingest.add_argument("--actor", default="system")
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
    p_export.add_argument("--repro-check", action="store_true", help="F9 reproducibility test")

    args = parser.parse_args(argv)

    if args.cmd == "ingest":
        snap = json.loads(Path(args.snapshot).read_text(encoding="utf-8"))
        outcome_raw = args.outcome
        if Path(outcome_raw).is_file():
            outcome = json.loads(Path(outcome_raw).read_text(encoding="utf-8"))
        else:
            outcome = json.loads(outcome_raw)
        entry = log_decision(
            snapshot=snap,
            outcome=outcome,
            actor=args.actor,
            database=args.database,
        )
        print(json.dumps(entry, indent=2))
        return 0

    if args.cmd == "check":
        ledger = AppendOnlyLedger(args.database)
        entries = ledger.list_entries()
        report = run_institutional_check(
            ledger=ledger,
            context={
                "ledger_entries": entries,
                "expected_count": len(entries),
                "actual_count": len(entries),
                "source_coverage_pct": 100.0,
            },
            observation_lane=args.observation_lane,
        )
        print(json.dumps(report.to_dict(), indent=2))
        return 0 if report.passed else 1

    if args.cmd == "verify-chain":
        ledger = AppendOnlyLedger(args.database)
        print(json.dumps(ledger.verify(), indent=2))
        return 0

    if args.cmd == "export":
        from inst_spine.export import build_audit_bundle, verify_bundle_reproducible

        if args.repro_check:
            ok, msg = verify_bundle_reproducible(args.database)
            print(json.dumps({"ok": ok, "message": msg}, indent=2))
            return 0 if ok else 1
        result = build_audit_bundle(
            args.database,
            out_dir=args.out_dir,
            tarball_path=args.tarball,
        )
        print(
            json.dumps(
                {
                    "ok": result.ok,
                    "bundle_sha256": result.bundle_sha256,
                    "tarball": str(result.tarball_path),
                    "validation": result.validation.message,
                },
                indent=2,
            )
        )
        return 0 if result.ok else 1

    return 1


if __name__ == "__main__":
    sys.exit(main())
