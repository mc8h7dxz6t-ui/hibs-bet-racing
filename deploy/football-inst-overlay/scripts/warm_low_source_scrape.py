#!/usr/bin/env python3
"""Headless low-source scrape cycle — FDO/FotMob/ESPN + thin-data rescue (cron-safe)."""

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
    from hibs_predictor.scrapers.robust_scrape_cycle import run_robust_scrape_cycle

    force = os.getenv("HIBS_LOW_SOURCE_SCRAPE_FORCE", "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    include_domestic = os.getenv("HIBS_FETCH_ALL_DOMESTIC", "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    agg = DataAggregator()
    report = run_robust_scrape_cycle(
        agg,
        include_domestic=include_domestic,
        force=force,
    )

    log_dir = Path(os.getenv("LOG_DIR", "/var/log/hibs-bet"))
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        status_path = log_dir / "low-source-scrape.json"
        status_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        robust_path = log_dir / "robust-scrape.json"
        if not robust_path.is_file():
            robust_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass

    print(json.dumps(report))
    if report.get("ok"):
        return 0
    if report.get("fixture_count", 0) > 0:
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
