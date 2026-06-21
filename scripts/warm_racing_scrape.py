#!/usr/bin/env python3
"""Headless racing robust scrape cycle — cron-safe."""

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
    from hibs_racing.scrapers.robust_scrape_cycle import run_robust_scrape_cycle

    force = os.getenv("HIBS_RACING_SCRAPE_FORCE", "0").strip().lower() in ("1", "true", "yes", "on")
    window = int(os.getenv("HIBS_RACING_SCRAPE_WINDOW", "48"))
    report = run_robust_scrape_cycle(force=force, window_hours=window, odds_source="auto")

    log_dir = Path(os.getenv("LOG_DIR", ROOT / "logs"))
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / "robust-racing-scrape.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass

    print(json.dumps(report))
    if report.get("ok"):
        return 0
    if int(report.get("runner_count") or 0) > 0:
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
