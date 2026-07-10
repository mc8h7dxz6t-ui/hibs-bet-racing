#!/usr/bin/env python3
"""Football pred-log-sync only — cross-platform prediction-results cron."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("HOME", str(ROOT))
os.environ.setdefault("DEPLOY_PATH", str(ROOT))


def main() -> int:
    from hibs_predictor.forward_evidence import ensure_audit_db, run_daily_clv_sync

    ensure_audit_db()
    result = run_daily_clv_sync()
    print(result)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
