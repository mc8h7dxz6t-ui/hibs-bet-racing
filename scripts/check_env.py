#!/usr/bin/env python3
"""Print hibs-racing credential readiness (no secret values)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from hibs_racing.web_service import health_status


def _flag(ok: bool) -> str:
    return "OK" if ok else "MISSING"


def main() -> int:
    h = health_status()
    rf = h.raceform_path
    rf_ok = bool(rf and Path(rf).exists())
    lines = [
        "hibs-racing .env check",
        f"  Racing API:    {_flag(h.racing_api)}",
        f"  Racing Post:   {_flag(h.racing_post)} (rpscrape fallback)",
        f"  Matchbook:     {_flag(h.matchbook)} (batch odds at 06:00)",
        f"  Mode:          analytics (no live execution)",
        f"  Raceform DB:   {_flag(rf_ok)}" + (f"  ({rf})" if rf else ""),
        f"  Feature store: {_flag(h.db_ok)}  runners={h.runners_loaded} scores={h.scores_loaded}",
        f"  Web:           PORT={os.environ.get('PORT', '5003')} HOST={os.environ.get('HOST', '127.0.0.1')}",
    ]
    print("\n".join(lines))
    if not h.racing_api:
        print("\n→ Set RACING_API_USERNAME + RACING_API_PASSWORD (required for Refresh 24h)", file=sys.stderr)
    if not h.matchbook:
        print("→ Set MATCHBOOK_USERNAME + MATCHBOOK_PASSWORD for exchange odds", file=sys.stderr)
    if not rf_ok:
        print("→ Set RACEFORM_DB_PATH to your Kaggle raceform.db", file=sys.stderr)
    return 0 if h.racing_api and rf_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
