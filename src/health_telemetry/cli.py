"""Health Telemetry CLI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from health_telemetry.ingest import ingest_batch
from inst_spine.cli_util import run_cli
from inst_spine.product_cli import (
    print_json,
    run_f9_check,
    run_institutional_export,
    run_institutional_verify,
)

PRODUCT = "health-telemetry"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="health-telemetry")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ingest = sub.add_parser("ingest", help="Ingest telemetry batch JSON")
    p_ingest.add_argument("--device-id", required=True)
    p_ingest.add_argument("--packets", required=True, help="JSON array file or inline JSON")
    p_ingest.add_argument("--database", type=Path, default=Path("data/health_telemetry.sqlite"))

    p_check = sub.add_parser("check", help="F1–F9 institutional check")
    p_check.add_argument("--database", type=Path, default=Path("data/health_telemetry.sqlite"))

    p_export = sub.add_parser("export", help="Audit bundle")
    p_export.add_argument("--database", type=Path, default=Path("data/health_telemetry.sqlite"))
    p_export.add_argument("--out-dir", type=Path, default=None)
    p_export.add_argument("--tarball", type=Path, default=None)
    p_export.add_argument("--repro-check", action="store_true")

    p_bundle = sub.add_parser("verify-bundle", help="Offline auditor replay")
    p_bundle.add_argument("--tarball", type=Path, required=True)

    args = parser.parse_args(argv)

    if args.cmd == "ingest":
        raw = args.packets
        p = Path(raw)
        data = json.loads(p.read_text(encoding="utf-8") if p.is_file() else raw)
        if not isinstance(data, list):
            raise ValueError("--packets must be a JSON array")
        entry = ingest_batch(device_id=args.device_id, packets=data, database=args.database)
        print_json({"ok": True, "entry": entry, "product": PRODUCT})
        return 0

    if args.cmd == "check":
        code, body = run_f9_check(args.database)
        print_json(body)
        return code

    if args.cmd == "export":
        code, body = run_institutional_export(
            args.database,
            product=PRODUCT,
            out_dir=args.out_dir,
            tarball=args.tarball,
            repro_check=args.repro_check,
        )
        print_json(body)
        return code

    if args.cmd == "verify-bundle":
        code, body = run_institutional_verify(args.tarball, product=PRODUCT)
        print_json(body)
        return code

    return 1


if __name__ == "__main__":
    run_cli(lambda: main())
