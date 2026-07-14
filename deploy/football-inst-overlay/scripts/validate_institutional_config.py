#!/usr/bin/env python3
"""Exit 1 when HIBS_PRODUCTION=1 and blocking institutional config issues exist."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")


def main() -> int:
    grade_a = "--grade-a" in sys.argv
    os.environ.setdefault("HIBS_PRODUCTION", "1")
    from hibs_predictor.institutional_readiness import collect_config_issues, readiness_dict

    issues, warnings = collect_config_issues(production=True)
    rep = readiness_dict()
    print(f"engineering_grade={rep.get('engineering_grade')} evidence_grade={rep.get('evidence_grade')}")
    for msg in issues:
        print(f"BLOCK: {msg}")
    for msg in warnings:
        print(f"WARN: {msg}")
    if grade_a:
        return 0 if rep.get("engineering_grade") == "A" and not issues and not warnings else 1
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
