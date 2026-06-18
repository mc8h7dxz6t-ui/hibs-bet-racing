"""Ad Guard CLI — evaluate outbound marketing API calls."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from inst_spine.ledger import AppendOnlyLedger

from ad_guard.proxy import AdGuardGateway, AdSpendRequest


async def _eval_once(args: argparse.Namespace) -> int:
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ad-guard", description="Inst++ Ad-Tech Budget Guardrail")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_eval = sub.add_parser("evaluate", help="Evaluate one outbound marketing API call")
    p_eval.add_argument("--client-id", default="agency-1")
    p_eval.add_argument("--campaign-id")
    p_eval.add_argument("--provider", default="generic", choices=["generic", "google", "meta"])
    p_eval.add_argument("--method", default="POST")
    p_eval.add_argument("--path", default="/v1/campaigns/mutate")
    p_eval.add_argument("--body", default="{}")
    p_eval.add_argument("--idempotency-key")
    p_eval.add_argument("--database", default="data/ad_guard_ledger.sqlite")
    p_eval.add_argument("--shadow", action="store_true", default=True)

    args = parser.parse_args(argv)
    if args.cmd == "evaluate":
        return asyncio.run(_eval_once(args))
    return 1


if __name__ == "__main__":
    sys.exit(main())
