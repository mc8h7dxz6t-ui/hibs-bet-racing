"""CLI for P2 audit bundle export."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from inst_spine.export import build_audit_bundle, verify_bundle_reproducible


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="inst-spine-export")
    parser.add_argument("database", type=Path, help="Ledger SQLite path")
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--tarball", type=Path, default=None)
    parser.add_argument("--repro-check", action="store_true", help="F9 reproducibility self-test")
    args = parser.parse_args(argv)

    if args.repro_check:
        ok, msg = verify_bundle_reproducible(args.database)
        print(json.dumps({"ok": ok, "message": msg}, indent=2))
        return 0 if ok else 1

    result = build_audit_bundle(
        args.database,
        out_dir=args.out_dir,
        tarball_path=args.tarball,
        abort_on_fail=True,
    )
    payload = {
        "ok": result.ok,
        "bundle_sha256": result.bundle_sha256,
        "tarball": str(result.tarball_path) if result.tarball_path else None,
        "out_dir": str(result.out_dir),
        "validation": {
            "genesis_ok": result.validation.genesis_ok,
            "chain_ok": result.validation.chain_ok,
            "lamport_ok": result.validation.lamport_ok,
            "message": result.validation.message,
        },
        "institutional_passed": result.institutional_passed,
    }
    print(json.dumps(payload, indent=2))
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
