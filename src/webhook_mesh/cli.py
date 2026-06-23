"""Webhook Mesh CLI — serve, replay, export, check, verify-bundle."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import hmac
import json
import os
import sys
from pathlib import Path

from inst_spine.cli_util import run_cli
from inst_spine.product_cli import (
    print_json,
    run_f9_check,
    run_institutional_export,
    run_institutional_verify,
)
from webhook_mesh.audit import ledger_path

PRODUCT = "webhook-mesh"


def _run_serve(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(description="Inst++ Webhook Idempotency Mesh")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--wal", default=None, help="WAL path (or INST_WAL_PATH env)")
    parser.add_argument("--ledger", default=None, help="Genesis ledger sqlite path")
    args = parser.parse_args(argv)
    if args.wal:
        os.environ["INST_WAL_PATH"] = args.wal
    if args.ledger:
        os.environ["WEBHOOK_MESH_LEDGER"] = args.ledger
    import uvicorn

    uvicorn.run(
        "webhook_mesh.serve:app",
        host=args.host,
        port=args.port,
        log_level="info",
    )


def _run_replay(argv: list[str]) -> int:
    from webhook_mesh.fsm import replay_dead_letter

    parser = argparse.ArgumentParser(description="Replay dead-letter with poison guards")
    parser.add_argument("--dead-letter-dir", default="./data/dead_letter")
    parser.add_argument("--manifest-id", default=None)
    parser.add_argument("--payload-id", default=None)
    parser.add_argument("--schema-version", default=None)
    args = parser.parse_args(argv)
    ok, message = asyncio.run(
        replay_dead_letter(
            args.dead_letter_dir,
            manifest_id=args.manifest_id,
            payload_id=args.payload_id,
            schema_version=args.schema_version,
        )
    )
    print(f"{'replay_ok' if ok else 'replay_failed'}: {message}")
    return 0 if ok else 1


def _run_demo_sign(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Sign a webhook body for ingress test")
    parser.add_argument("--secret", required=True)
    parser.add_argument("--body-file", type=Path, required=True)
    args = parser.parse_args(argv)
    body = args.body_file.read_bytes()
    sig = hmac.new(args.secret.encode(), body, hashlib.sha256).hexdigest()
    print_json({"signature": sig, "body_sha256": hashlib.sha256(body).hexdigest()})
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        _run_serve([])
        return 0
    cmd = argv[0]
    if cmd == "serve":
        _run_serve(argv[1:])
        return 0
    if cmd == "replay":
        return _run_replay(argv[1:])
    if cmd == "demo-sign":
        return _run_demo_sign(argv[1:])

    if cmd == "check":
        parser = argparse.ArgumentParser(prog="webhook-mesh check")
        parser.add_argument("--database", type=Path, default=None)
        args = parser.parse_args(argv[1:])
        db = args.database or ledger_path()
        code, body = run_f9_check(db)
        print_json(body)
        return code

    if cmd == "export":
        parser = argparse.ArgumentParser(prog="webhook-mesh export")
        parser.add_argument("--database", type=Path, default=None)
        parser.add_argument("--out-dir", type=Path, default=None)
        parser.add_argument("--tarball", type=Path, default=None)
        parser.add_argument("--repro-check", action="store_true")
        args = parser.parse_args(argv[1:])
        db = args.database or ledger_path()
        code, body = run_institutional_export(
            db,
            product=PRODUCT,
            out_dir=args.out_dir,
            tarball=args.tarball,
            repro_check=args.repro_check,
        )
        print_json(body)
        return code

    if cmd == "verify-bundle":
        parser = argparse.ArgumentParser(prog="webhook-mesh verify-bundle")
        parser.add_argument("--tarball", type=Path, required=True)
        args = parser.parse_args(argv[1:])
        code, body = run_institutional_verify(args.tarball, product=PRODUCT)
        print_json(body)
        return code

    print(f"unknown command: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    run_cli(lambda: main())
