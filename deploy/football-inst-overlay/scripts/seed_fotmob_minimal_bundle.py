#!/usr/bin/env python3
"""Minimal scrape-first bundle seed — FotMob/FDO/ESPN without API-Sports."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")


def main() -> int:
    from hibs_predictor.data_aggregator import DataAggregator
    from hibs_predictor.data_producer_slo import football_fixture_bundle_status
    from hibs_predictor.scrapers.low_source_api import run_low_source_scrape_cycle

    include_domestic = os.getenv("HIBS_FETCH_ALL_DOMESTIC", "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    agg = DataAggregator()
    report = run_low_source_scrape_cycle(
        agg,
        include_domestic=include_domestic,
        force=True,
        backfill_bundle=True,
    )
    bundle = football_fixture_bundle_status(include_domestic=include_domestic)
    payload = {
        "ok": int(bundle.get("fixture_count") or 0) > 0,
        "fixture_count": int(bundle.get("fixture_count") or 0),
        "scrape": report,
    }
    print(json.dumps(payload, indent=2))
    return 0 if payload["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
