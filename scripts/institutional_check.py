#!/usr/bin/env python3
"""Institutional++ check — snapshots, gate regression, optional paper recon."""

from __future__ import annotations

import argparse
import json
import sys

from hibs_racing.institutional.check import run_institutional_check


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=90)
    p.add_argument("--card-date")
    p.add_argument("--require-snapshots", action="store_true", default=True)
    p.add_argument("--no-require-snapshots", action="store_false", dest="require_snapshots")
    p.add_argument("--require-recon-clean", action="store_true")
    args = p.parse_args()
    report = run_institutional_check(
        days=args.days,
        card_date=args.card_date,
        require_snapshots=args.require_snapshots,
        require_recon_clean=args.require_recon_clean,
    )
    print(json.dumps(report.to_dict(), indent=2))
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
