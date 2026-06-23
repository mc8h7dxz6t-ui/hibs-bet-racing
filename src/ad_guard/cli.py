"""Ad Guard CLI — evaluate, serve, check, export, verify-bundle."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from ad_guard.proxy import AdGuardGateway, AdSpendRequest
from inst_spine.cli_util import run_cli
from inst_spine.ledger import AppendOnlyLedger
from inst_spine.product_cli import (
    print_json,
    run_f9_check,
    run_institutional_export,
    run_institutional_verify,
)

PRODUCT = "ad-guard"


async def _eval_once(args: argparse.Namespace) -> int:
    ledger = AppendOnlyLedger(args.database, async_writes=True) if args.database else None
    if ledger:
        ledger.start_async_writer()
    gw = AdGuardGateway(
        ledger=ledger,
        shadow_mode=not args.live,
        upstream_base=os.environ.get("AD_GUARD_UPSTREAM_BASE"),
    )
    body = json.loads(args.body)
    req = AdSpendRequest(
        client_id=args.client_id,
        method=args.method,
        path=args.path,
        body=body,
        provider=args.provider,
        campaign_id=args.campaign_id,
        idempotency_key=args.idempotency_key,
    )
    resp = await gw.evaluate(req)
    print_json(
        {
            "decision": resp.decision.value,
            "reason": resp.reason,
            "upstream_status": resp.upstream_status,
            "live": args.live,
        }
    )
    if ledger:
        ledger.stop_async_writer(flush=True)
        print_json(ledger.verify())
    return 0 if resp.decision.value == "approve" else 1


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] not in {"evaluate", "serve", "export", "check", "verify-bundle"}:
        argv = ["evaluate"] + argv

    cmd = argv[0]
    if cmd == "evaluate":
        parser = argparse.ArgumentParser(prog="ad-guard evaluate")
        parser.add_argument("--client-id", default="agency-1")
        parser.add_argument("--campaign-id")
        parser.add_argument("--provider", default="generic", choices=["generic", "google", "meta"])
        parser.add_argument("--method", default="POST")
        parser.add_argument("--path", default="/v1/campaigns/mutate")
        parser.add_argument("--body", default="{}")
        parser.add_argument("--idempotency-key")
        parser.add_argument("--database", type=Path, default=Path("data/ad_guard_ledger.sqlite"))
        parser.add_argument("--live", action="store_true", help="Live upstream forward")
        return asyncio.run(_eval_once(parser.parse_args(argv[1:])))

    if cmd == "serve":
        parser = argparse.ArgumentParser(prog="ad-guard serve")
        parser.add_argument("--host", default="0.0.0.0")
        parser.add_argument("--port", type=int, default=8788)
        parser.add_argument("--database", default="data/ad_guard_ledger.sqlite")
        parser.add_argument("--live", action="store_true")
        args = parser.parse_args(argv[1:])
        os.environ["AD_GUARD_DATABASE"] = args.database
        os.environ["AD_GUARD_SHADOW"] = "0" if args.live else "1"
        import uvicorn

        uvicorn.run("ad_guard.serve:app", host=args.host, port=args.port, log_level="info")
        return 0

    if cmd == "check":
        parser = argparse.ArgumentParser(prog="ad-guard check")
        parser.add_argument("--database", type=Path, default=Path("data/ad_guard_ledger.sqlite"))
        args = parser.parse_args(argv[1:])
        code, body = run_f9_check(args.database)
        print_json(body)
        return code

    if cmd == "export":
        parser = argparse.ArgumentParser(prog="ad-guard export")
        parser.add_argument("--database", type=Path, default=Path("data/ad_guard_ledger.sqlite"))
        parser.add_argument("--out-dir", type=Path, default=None)
        parser.add_argument("--tarball", type=Path, default=None)
        parser.add_argument("--repro-check", action="store_true")
        args = parser.parse_args(argv[1:])
        code, body = run_institutional_export(
            args.database,
            product=PRODUCT,
            out_dir=args.out_dir,
            tarball=args.tarball,
            repro_check=args.repro_check,
        )
        print_json(body)
        return code

    if cmd == "verify-bundle":
        parser = argparse.ArgumentParser(prog="ad-guard verify-bundle")
        parser.add_argument("--tarball", type=Path, required=True)
        parser.add_argument("--anchor", type=Path, default=None)
        parser.add_argument("--sha256", default=None)
        args = parser.parse_args(argv[1:])
        code, body = run_institutional_verify(
            args.tarball,
            product=PRODUCT,
            anchor=args.anchor,
            expected_sha256=args.sha256,
        )
        print_json(body)
        return code

    return 1


if __name__ == "__main__":
    run_cli(lambda: main())
