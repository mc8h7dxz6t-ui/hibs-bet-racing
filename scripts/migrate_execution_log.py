#!/usr/bin/env python3
"""Apply execution_log schema to the hibs-racing feature store (idempotent)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from hibs_racing.config import db_path, load_config
from hibs_racing.live.execution_log import ensure_execution_log_schema, execution_log_summary


def main() -> int:
    db = ensure_execution_log_schema(db_path(load_config()))
    summary = execution_log_summary(database=db)
    print("execution_log migration OK")
    print(f"  database:     {db}")
    print(f"  total rows:   {summary['total_rows']}")
    print(f"  live routed:  {summary['live_routed']}")
    if summary["last_batch_id"]:
        print(f"  last batch:   {summary['last_batch_id']} @ {summary['last_created_at']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
