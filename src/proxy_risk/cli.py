"""Proxy-Risk CLI."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from inst_spine.check import build_compliance_context, run_institutional_check
from inst_spine.cli_util import run_cli
from inst_spine.ledger import AppendOnlyLedger
from proxy_risk.router import ProxyRequest, ProxyRiskGateway

PRODUCT = "proxy-risk"


def _use_uvloop() -> None:
    try:
        import uvloop

        uvloop.install()
    except ImportError:
        pass


async def _eval_once(args: argparse.Namespace) -> int:
    ledger = AppendOnlyLedger(args.database, async_writes=True) if args.database else None
    if ledger:
        ledger.start_async_writer()
    gw = ProxyRiskGateway(ledger=ledger, shadow_mode=not args.live)
    body = json.loads(args.body)
    req = ProxyRequest(
        client_id=args.client_id,
        method=args.method,
        path=args.path,
        body=body,
        idempotency_key=args.idempotency_key,
        reference_price=args.reference_price,
    )
    resp = await gw.evaluate(req)
    print(
        json.dumps(
            {
                "decision": resp.decision.value,
                "reason": resp.reason,
                "upstream_status": resp.upstream_status,
                "upstream_body": resp.upstream_body,
            },
            indent=2,
        )
    )
    if ledger:
        ledger.stop_async_writer(flush=True)
        print(json.dumps(ledger.verify(), indent=2))
    return 0 if resp.decision.value == "approve" else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="proxy-risk")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_eval = sub.add_parser("evaluate", help="Evaluate one request through gates")
    p_eval.add_argument("--client-id", default="test-client")
    p_eval.add_argument("--method", default="POST")
    p_eval.add_argument("--path", default="/orders")
    p_eval.add_argument("--body", default="{}")
    p_eval.add_argument("--idempotency-key")
    p_eval.add_argument("--reference-price", type=float)
    p_eval.add_argument("--database", default="data/proxy_risk_ledger.sqlite")
    p_eval.add_argument("--live", action="store_true", help="Forward to upstream after gates")

    p_check = sub.add_parser("check", help="Run F1–F9 institutional check on proxy ledger")
    p_check.add_argument("--database", type=Path, default=Path("data/proxy_risk_ledger.sqlite"))
    p_check.add_argument("--observation-lane", action="store_true")

    p_export = sub.add_parser("export", help="P2 deterministic audit bundle (tar + sha256)")
    p_export.add_argument("--database", type=Path, default=Path("data/proxy_risk_ledger.sqlite"))
    p_export.add_argument("--out-dir", type=Path, default=None)
    p_export.add_argument("--tarball", type=Path, default=None)
    p_export.add_argument("--anchor", type=Path, default=None)
    p_export.add_argument("--repro-check", action="store_true", help="F9 reproducibility test")

    p_bundle = sub.add_parser("verify-bundle", help="Offline auditor dry-run on exported tarball")
    p_bundle.add_argument("--tarball", type=Path, required=True)
    p_bundle.add_argument("--anchor", type=Path, default=None)
    p_bundle.add_argument("--sha256", default=None)

    p_serve = sub.add_parser("serve", help="Run HTTP gateway server")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=18443)
    p_serve.add_argument("--database", default="data/proxy_risk_ledger.sqlite")
    p_serve.add_argument("--live", action="store_true", help="Enable upstream forward")
    p_serve.add_argument("--uvloop", action="store_true", default=True)

    args = parser.parse_args(argv)

    if args.cmd == "evaluate":
        return asyncio.run(_eval_once(args))

    if args.cmd == "check":
        ledger = AppendOnlyLedger(args.database)
        ctx = build_compliance_context(ledger, run_f9=True)
        report = run_institutional_check(
            ledger=ledger,
            context=ctx,
            observation_lane=args.observation_lane,
            run_f9=False,
        )
        print(json.dumps(report.to_dict(), indent=2))
        return 0 if report.passed else 1

    if args.cmd == "export":
        from inst_spine.export import build_audit_bundle, verify_bundle_reproducible

        if args.repro_check:
            ok, msg = verify_bundle_reproducible(args.database)
            print(json.dumps({"ok": ok, "message": msg, "product": PRODUCT}, indent=2))
            return 0 if ok else 1
        result = build_audit_bundle(
            args.database,
            out_dir=args.out_dir,
            tarball_path=args.tarball,
            anchor_path=args.anchor,
            product=PRODUCT,
        )
        print(
            json.dumps(
                {
                    "ok": result.ok,
                    "product": PRODUCT,
                    "bundle_sha256": result.bundle_sha256,
                    "tarball": str(result.tarball_path) if result.tarball_path else None,
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

    if args.cmd == "serve":
        if args.uvloop:
            _use_uvloop()
        from proxy_risk.router import serve_shadow_demo

        asyncio.run(
            serve_shadow_demo(
                host=args.host,
                port=args.port,
                shadow_mode=not args.live,
                database=args.database,
            )
        )
        return 0

    return 1


if __name__ == "__main__":
    run_cli(lambda: main())
