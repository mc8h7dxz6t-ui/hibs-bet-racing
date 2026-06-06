#!/usr/bin/env python3
"""CLI entry: batch historical enrich recovery (Nov 2025 → May 2026 dense window)."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hibs_racing.ingest.batch_enrich_recovery import run_batch_enrich_recovery  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Batch scrape RP racecards + backfill historical runner enrich columns.",
    )
    parser.add_argument("--start", default=None, help="Start date YYYY-MM-DD (default: config)")
    parser.add_argument("--end", default=None, help="End date YYYY-MM-DD (default: config)")
    parser.add_argument("--max-days", type=int, help="Process at most N days (pilot block)")
    parser.add_argument("--no-resume", action="store_true", help="Ignore checkpoint file")
    parser.add_argument("--refetch", action="store_true", help="Re-fetch even when JSON exists")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    report = run_batch_enrich_recovery(
        start=args.start,
        end=args.end,
        resume=not args.no_resume,
        max_days=args.max_days,
        skip_existing_json=not args.refetch,
    )
    print(json.dumps(report.to_dict(), indent=2))
    print(f"FINAL_HISTORICAL_COVERAGE={report.final_coverage_pct:.2f}%")
    return 0 if report.days_failed == 0 or report.final_coverage_pct > report.initial_coverage_pct else 1


if __name__ == "__main__":
    raise SystemExit(main())
