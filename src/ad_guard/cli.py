"""Ad Guard CLI — evaluate, serve, export."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys


async def _eval_once(args: argparse.Namespace) -> int:
    from inst_spine.ledger import AppendOnlyLedger

    from ad_guard.proxy import AdGuardGateway, AdSpendRequest

    ledger = AppendOnlyLedger(args.database, async_writes=True) if args.database else None
    if ledger:
        ledger.start_async_writer()
    gw = AdGuardGateway(ledger=ledger, shadow_mode=args.shadow)
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
    print(json.dumps({"decision": resp.decision.value, "reason": resp.reason}, indent=2))
    if ledger:
        ledger.stop_async_writer(flush=True)
        print(json.dumps(ledger.verify(), indent=2))
    return 0 if resp.decision.value == "approve" else 1


def _run_serve(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Run Ad Guard HTTP proxy")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8788)
    parser.add_argument("--database", default="data/ad_guard_ledger.sqlite")
    parser.add_argument("--live", action="store_true", help="Disable shadow mode")
    args = parser.parse_args(argv)
    os.environ["AD_GUARD_DATABASE"] = args.database
    os.environ["AD_GUARD_SHADOW"] = "0" if args.live else "1"
    import uvicorn

    uvicorn.run("ad_guard.serve:app", host=args.host, port=args.port, log_level="info")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] not in {"evaluate", "serve", "export"}:
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
        parser.add_argument("--database", default="data/ad_guard_ledger.sqlite")
        parser.add_argument("--shadow", action="store_true", default=True)
        return asyncio.run(_eval_once(parser.parse_args(argv[1:])))
    if cmd == "serve":
        return _run_serve(argv[1:])
    if cmd == "export":
        from pathlib import Path

        parser = argparse.ArgumentParser(prog="ad-guard export")
        parser.add_argument("--database", type=Path, default=Path("data/ad_guard_ledger.sqlite"))
        parser.add_argument("--out-dir", type=Path, default=None)
        parser.add_argument("--tarball", type=Path, default=None)
        parser.add_argument("--repro-check", action="store_true")
        args = parser.parse_args(argv[1:])
        from inst_spine.export import build_audit_bundle, verify_bundle_reproducible

        if args.repro_check:
            ok, msg = verify_bundle_reproducible(args.database)
            print(json.dumps({"ok": ok, "message": msg, "product": "ad-guard"}, indent=2))
            return 0 if ok else 1
        result = build_audit_bundle(
            args.database,
            out_dir=args.out_dir,
            tarball_path=args.tarball,
            abort_on_fail=True,
        )
        print(
            json.dumps(
                {
                    "ok": result.ok,
                    "product": "ad-guard",
                    "bundle_sha256": result.bundle_sha256,
                    "tarball": str(result.tarball_path) if result.tarball_path else None,
                },
                indent=2,
            )
        )
        return 0 if result.ok else 1
    return 1


if __name__ == "__main__":
    sys.exit(main())
