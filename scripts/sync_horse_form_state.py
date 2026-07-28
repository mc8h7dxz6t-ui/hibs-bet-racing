#!/usr/bin/env python3
"""Autonomous horse form state sync — speed delta EWMA + sample σ."""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync horse_form_state from runners")
    parser.add_argument("--since", default=os.getenv("HIBS_HORSE_STATE_SINCE", "2024-07-01"))
    parser.add_argument("--limit", type=int, default=int(os.getenv("HIBS_HORSE_STATE_LIMIT", "50000")))
    args = parser.parse_args()
    from hibs_racing.features.horse_form_state import sync_horse_form_state_from_runners

    report = sync_horse_form_state_from_runners(since=args.since, limit=args.limit)
    print(report)
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
