"""Webhook Replay CLI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from inst_spine.cli_util import run_cli
from inst_spine.ledger import AppendOnlyLedger
from inst_spine.product_cli import (
    print_json,
    run_f9_check,
    run_institutional_export,
    run_institutional_verify,
)

from webhook_replay.capture import CaptureManifest, CaptureStore
from webhook_replay.integrate import capture_from_ingress
from webhook_replay.replay_engine import ReplayEngine

PRODUCT = "webhook-replay"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="webhook-replay")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_cap = sub.add_parser("capture", help="Capture one webhook for offline replay")
    p_cap.add_argument("--capture-id", required=True)
    p_cap.add_argument("--tenant-id", default="tenant-demo")
    p_cap.add_argument("--provider", default="generic")
    p_cap.add_argument("--body-file", type=Path, required=True)
    p_cap.add_argument("--store-dir", type=Path, default=Path("data/webhook_captures"))
    p_cap.add_argument("--header", action="append", default=[], help="Header as Key:Value")

    p_rep = sub.add_parser("replay", help="Replay one capture or all in store")
    p_rep.add_argument("--store-dir", type=Path, default=Path("data/webhook_captures"))
    p_rep.add_argument("--capture-id", default=None)
    p_rep.add_argument("--file", type=Path, default=None)
    p_rep.add_argument("--database", type=Path, default=None)
    p_rep.add_argument("--all", action="store_true")

    p_check = sub.add_parser("check", help="F1–F9 institutional check")
    p_check.add_argument("--database", type=Path, default=Path("data/webhook_replay.sqlite"))

    p_export = sub.add_parser("export", help="Deterministic audit bundle")
    p_export.add_argument("--database", type=Path, default=Path("data/webhook_replay.sqlite"))
    p_export.add_argument("--out-dir", type=Path, default=None)
    p_export.add_argument("--tarball", type=Path, default=None)
    p_export.add_argument("--repro-check", action="store_true")

    p_bundle = sub.add_parser("verify-bundle", help="Offline auditor replay")
    p_bundle.add_argument("--tarball", type=Path, required=True)

    args = parser.parse_args(argv)

    if args.cmd == "capture":
        body = args.body_file.read_bytes()
        headers: dict[str, str] = {}
        for h in args.header:
            if ":" in h:
                k, v = h.split(":", 1)
                headers[k.strip()] = v.strip()
        path = capture_from_ingress(
            capture_id=args.capture_id,
            tenant_id=args.tenant_id,
            body=body,
            headers=headers,
            provider=args.provider,
            store_dir=args.store_dir,
        )
        print_json({"ok": True, "capture_path": str(path), "product": PRODUCT})
        return 0

    if args.cmd == "replay":
        store = CaptureStore(args.store_dir)
        ledger = AppendOnlyLedger(args.database) if args.database else None
        engine = ReplayEngine(store, ledger=ledger)
        if args.all:
            results = engine.replay_all()
            print_json(
                {
                    "ok": all(r.ok for r in results),
                    "product": PRODUCT,
                    "count": len(results),
                    "results": [r.to_dict() for r in results],
                }
            )
            return 0 if all(r.ok for r in results) else 1
        if args.file:
            result = engine.replay_file(args.file)
        elif args.capture_id:
            manifest, body = store.read_by_id(args.capture_id)
            result = engine.replay_capture(manifest, body)
        else:
            print_json({"ok": False, "error": "specify --capture-id, --file, or --all"})
            return 2
        print_json({"ok": result.ok, "product": PRODUCT, **result.to_dict()})
        return 0 if result.ok else 1

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
