"""Health Telemetry CLI."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from health_telemetry.export import build_health_audit_bundle
from health_telemetry.ingest import ingest_batch
from inst_spine.cli_util import run_cli
from inst_spine.product_cli import (
    print_json,
    run_f9_check,
    run_institutional_verify,
)

PRODUCT = "health-telemetry"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="health-telemetry",
        description="Device telemetry batch ingest — schema, sequence gate, tamper-evident ledger",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ingest = sub.add_parser("ingest", help="Ingest telemetry batch JSON")
    p_ingest.add_argument("--device-id", required=True)
    p_ingest.add_argument("--packets", required=True, help="JSON array file or inline JSON")
    p_ingest.add_argument("--database", type=Path, default=Path("data/health_telemetry.sqlite"))
    p_ingest.add_argument(
        "--profile",
        default="rpm_standard",
        choices=["rpm_standard", "vitals_only", "minimal"],
    )
    p_ingest.add_argument(
        "--skip-sequence-gate",
        action="store_true",
        help="Dev only — bypass per-device monotonic seq enforcement",
    )

    p_check = sub.add_parser("check", help="F1–F9 institutional check")
    p_check.add_argument("--database", type=Path, default=Path("data/health_telemetry.sqlite"))
    p_check.add_argument(
        "--observation-lane",
        action="store_true",
        help="Blocking subset only (chain/genesis/lamport) for ward burn-in",
    )

    p_export = sub.add_parser("export", help="Audit bundle")
    p_export.add_argument("--database", type=Path, default=Path("data/health_telemetry.sqlite"))
    p_export.add_argument("--out-dir", type=Path, default=None)
    p_export.add_argument("--tarball", type=Path, default=None)
    p_export.add_argument("--repro-check", action="store_true")
    p_export.add_argument(
        "--observation-lane",
        action="store_true",
        help="PHI-safe export — raw packets redacted, summaries + chain retained",
    )

    p_bundle = sub.add_parser("verify-bundle", help="Offline auditor replay")
    p_bundle.add_argument("--tarball", type=Path, required=True)

    p_serve = sub.add_parser("serve", help="HTTP WAL-before-ack batch ingress")
    p_serve.add_argument("--host", default=None)
    p_serve.add_argument("--port", type=int, default=None)

    args = parser.parse_args(argv)

    if args.cmd == "ingest":
        raw = args.packets
        p = Path(raw)
        data = json.loads(p.read_text(encoding="utf-8") if p.is_file() else raw)
        if not isinstance(data, list):
            raise ValueError("--packets must be a JSON array")
        entry = ingest_batch(
            device_id=args.device_id,
            packets=data,
            database=args.database,
            profile=args.profile,
            skip_sequence_gate=args.skip_sequence_gate,
        )
        print_json({"ok": True, "entry": entry, "product": PRODUCT})
        return 0

    if args.cmd == "check":
        code, body = run_f9_check(
            args.database,
            observation_lane=args.observation_lane,
        )
        print_json(body)
        return code

    if args.cmd == "export":
        if args.repro_check:
            from inst_spine.export import verify_bundle_reproducible

            ok, msg = verify_bundle_reproducible(args.database)
            print_json({"ok": ok, "message": msg, "product": PRODUCT})
            return 0 if ok else 1

        result = build_health_audit_bundle(
            args.database,
            out_dir=args.out_dir,
            tarball_path=args.tarball,
            observation_lane=args.observation_lane,
            product=PRODUCT,
        )
        body = {
            "ok": result.ok,
            "product": PRODUCT,
            "bundle_sha256": result.bundle_sha256,
            "tarball": str(result.tarball_path) if result.tarball_path else None,
            "validation": result.validation.message,
            "institutional_passed": result.institutional_passed,
            "observation_lane": args.observation_lane,
        }
        print_json(body)
        return 0 if result.ok else 1

    if args.cmd == "verify-bundle":
        code, body = run_institutional_verify(args.tarball, product=PRODUCT)
        print_json(body)
        return code

    if args.cmd == "serve":
        from health_telemetry.serve import main as serve_main

        if args.host:
            os.environ["HEALTH_TELEMETRY_HOST"] = args.host
        if args.port:
            os.environ["HEALTH_TELEMETRY_PORT"] = str(args.port)
        serve_main()
        return 0

    return 1


if __name__ == "__main__":
    run_cli(lambda: main())
