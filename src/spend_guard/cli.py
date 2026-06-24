"""Spend Guard CLI."""

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

from spend_guard.gateway import SpendGuardGateway, SpendRequest
from spend_guard.wallet import SpendWallet

PRODUCT = "spend-guard"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="spend-guard")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init-wallet", help="Create or reset demo wallet")
    p_init.add_argument("--wallet-db", type=Path, default=Path("data/spend_guard_wallet.sqlite"))
    p_init.add_argument("--balance", type=float, default=1000.0)

    p_reserve = sub.add_parser("reserve", help="Reserve spend before API dispatch")
    p_reserve.add_argument("--request-id", required=True)
    p_reserve.add_argument("--cost", type=float, required=True)
    p_reserve.add_argument("--wallet-db", type=Path, default=Path("data/spend_guard_wallet.sqlite"))
    p_reserve.add_argument("--ledger-db", type=Path, default=Path("data/spend_guard.sqlite"))
    p_reserve.add_argument("--shadow", action="store_true")

    p_settle = sub.add_parser("settle", help="Settle a reserved hold")
    p_settle.add_argument("--hold-id", required=True)
    p_settle.add_argument("--request-id", required=True)
    p_settle.add_argument("--actual-cost", type=float, required=True)
    p_settle.add_argument("--wallet-db", type=Path, default=Path("data/spend_guard_wallet.sqlite"))
    p_settle.add_argument("--ledger-db", type=Path, default=Path("data/spend_guard.sqlite"))

    p_status = sub.add_parser("status", help="Wallet status")
    p_status.add_argument("--wallet-db", type=Path, default=Path("data/spend_guard_wallet.sqlite"))

    p_demo = sub.add_parser("demo-drift-lock", help="Run reserve/settle loop until drift lockout")
    p_demo.add_argument("--wallet-db", type=Path, default=Path("data/spend_guard_wallet.sqlite"))
    p_demo.add_argument("--ledger-db", type=Path, default=Path("data/spend_guard.sqlite"))
    p_demo.add_argument("--spend", type=float, default=200.0)
    p_demo.add_argument("--big-spend", type=float, default=250.0)
    p_demo.add_argument("--iterations", type=int, default=8)

    p_check = sub.add_parser("check", help="F1–F9 institutional check")
    p_check.add_argument("--database", type=Path, default=Path("data/spend_guard.sqlite"))

    p_export = sub.add_parser("export", help="Deterministic audit bundle")
    p_export.add_argument("--database", type=Path, default=Path("data/spend_guard.sqlite"))
    p_export.add_argument("--out-dir", type=Path, default=None)
    p_export.add_argument("--tarball", type=Path, default=None)
    p_export.add_argument("--repro-check", action="store_true")

    p_bundle = sub.add_parser("verify-bundle", help="Offline auditor replay")
    p_bundle.add_argument("--tarball", type=Path, required=True)

    args = parser.parse_args(argv)

    if args.cmd == "init-wallet":
        if args.wallet_db.exists():
            args.wallet_db.unlink()
        wallet = SpendWallet(args.wallet_db, initial_balance=args.balance)
        print_json({"ok": True, "wallet": wallet.to_dict()})
        return 0

    if args.cmd == "reserve":
        wallet = SpendWallet(args.wallet_db)
        ledger = AppendOnlyLedger(args.ledger_db)
        gw = SpendGuardGateway(wallet=wallet, ledger=ledger, shadow_mode=args.shadow)
        resp = gw.reserve(SpendRequest(request_id=args.request_id, estimated_cost=args.cost))
        print_json({"ok": resp.decision.value == "approve", "product": PRODUCT, **resp.to_dict()})
        return 0 if resp.decision.value == "approve" else 1

    if args.cmd == "settle":
        wallet = SpendWallet(args.wallet_db)
        ledger = AppendOnlyLedger(args.ledger_db)
        gw = SpendGuardGateway(wallet=wallet, ledger=ledger)
        resp = gw.settle(args.hold_id, actual_cost=args.actual_cost, request_id=args.request_id)
        print_json({"ok": resp.decision.value in ("approve", "locked"), "product": PRODUCT, **resp.to_dict()})
        return 0 if resp.decision.value != "reject" else 1

    if args.cmd == "status":
        wallet = SpendWallet(args.wallet_db)
        print_json({"ok": True, "wallet": wallet.to_dict()})
        return 0

    if args.cmd == "demo-drift-lock":
        if args.wallet_db.exists():
            args.wallet_db.unlink()
        if args.ledger_db.exists():
            args.ledger_db.unlink()
        wallet = SpendWallet(args.wallet_db, initial_balance=1000.0, drift_threshold_pct=0.3)
        ledger = AppendOnlyLedger(args.ledger_db)
        gw = SpendGuardGateway(wallet=wallet, ledger=ledger)
        events = []
        locked = False
        for i in range(args.iterations):
            rid = f"demo-req-{i}"
            cost = args.spend if i < args.iterations - 1 else args.big_spend
            r = gw.reserve(SpendRequest(request_id=rid, estimated_cost=cost))
            if r.decision.value != "approve":
                events.append({"step": i, "phase": "reserve", **r.to_dict()})
                locked = r.decision.value == "locked"
                break
            s = gw.settle(r.hold_id or "", actual_cost=cost, request_id=rid)
            events.append({"step": i, "phase": "settle", **s.to_dict()})
            if s.decision.value == "locked":
                locked = True
                break
        print_json({"ok": True, "locked": locked, "events": events, "wallet": wallet.to_dict()})
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
