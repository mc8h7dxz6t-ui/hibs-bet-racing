#!/usr/bin/env python3
"""Weekly gate regression entrypoint (exit 0 = pass, 1 = fail)."""

from __future__ import annotations

import argparse
import json
import sys

from hibs_racing.backtest.gate_regression import run_gate_regression_check


def main() -> int:
    p = argparse.ArgumentParser(description="Gate1 regression check for CI / cron")
    p.add_argument("--days", type=int, default=90)
    p.add_argument("--start")
    p.add_argument("--end")
    p.add_argument("--require-snapshots", action="store_true")
    args = p.parse_args()
    check = run_gate_regression_check(
        days=args.days,
        start=args.start,
        end=args.end,
        require_snapshots=args.require_snapshots,
    )
    print(json.dumps(check.to_dict(), indent=2))
    return 0 if check.passed else 1


if __name__ == "__main__":
    sys.exit(main())
