#!/usr/bin/env python3
"""CLI entry for ranker preflight (cron, Docker, VPS)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hibs_racing.models.ranker_preflight import RankerPreflightError, verify_production_ranker


def main() -> int:
    try:
        report = verify_production_ranker(ROOT)
    except RankerPreflightError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
