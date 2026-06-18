"""CLI entry for webhook mesh HTTP server and DLQ replay."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import hmac
import json
import os
import sys
from pathlib import Path


def _run_serve(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(description="Inst++ Webhook Idempotency Mesh")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--wal", default=None, help="WAL path (or INST_WAL_PATH env)")
    args = parser.parse_args(argv)
    if args.wal:
        os.environ["INST_WAL_PATH"] = args.wal
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
    """Generate HMAC signature for manual ingress testing."""
    parser = argparse.ArgumentParser(description="Sign a webhook body for ingress test")
    parser.add_argument("--secret", required=True)
    parser.add_argument("--body-file", type=Path, required=True)
    args = parser.parse_args(argv)
    body = args.body_file.read_bytes()
    sig = hmac.new(args.secret.encode(), body, hashlib.sha256).hexdigest()
    print(json.dumps({"signature": sig, "body_sha256": hashlib.sha256(body).hexdigest()}))
    return 0


def main() -> None:
    argv = sys.argv[1:]
    if not argv or argv[0].startswith("-"):
        _run_serve(argv)
        return
    if argv[0] == "serve":
        _run_serve(argv[1:])
        return
    if argv[0] == "replay":
        raise SystemExit(_run_replay(argv[1:]))
    if argv[0] == "demo-sign":
        raise SystemExit(_run_demo_sign(argv[1:]))
    print(f"unknown command: {argv[0]}", file=sys.stderr)
    raise SystemExit(2)


if __name__ == "__main__":
    main()
