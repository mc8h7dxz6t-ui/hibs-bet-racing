"""Proxy-Risk CLI."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from inst_spine.ledger import AppendOnlyLedger
from proxy_risk.router import ProxyRequest, ProxyRiskGateway


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
    gw = ProxyRiskGateway(ledger=ledger, shadow_mode=args.shadow)
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
    print(json.dumps({"decision": resp.decision.value, "reason": resp.reason}, indent=2))
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
    p_eval.add_argument("--shadow", action="store_true", default=True)

    p_serve = sub.add_parser("serve", help="Run shadow HTTP server")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=18443)
    p_serve.add_argument("--uvloop", action="store_true", default=True)

    args = parser.parse_args(argv)

    if args.cmd == "evaluate":
        return asyncio.run(_eval_once(args))

    if args.cmd == "serve":
        if args.uvloop:
            _use_uvloop()
        from proxy_risk.router import serve_shadow_demo

        asyncio.run(serve_shadow_demo(host=args.host, port=args.port))
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
