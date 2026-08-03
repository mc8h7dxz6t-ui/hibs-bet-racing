#!/usr/bin/env python3
"""Hands-off racing execution pass — build intents from today's card and route."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run racing staking execution pass")
    parser.add_argument("--card-date", help="ISO card date (default: UTC today)")
    parser.add_argument("--limit", type=int, default=0, help="Max intents (0 = no limit)")
    parser.add_argument("--log", action="store_true", help="Append results to execution log")
    args = parser.parse_args()

    import pandas as pd

    from hibs_racing.config import db_path, load_config
    from hibs_racing.features.store import connect, init_db
    from hibs_racing.live.execution_config import EXECUTION_DISABLED_MSG, execution_summary
    from hibs_racing.live.execution_router import build_execution_intents, route_execution_batch
    from hibs_racing.odds.market_steam import evaluate_market_gauges

    cfg = load_config()
    db = db_path(cfg)
    init_db(db)
    card_date = args.card_date or datetime.now(timezone.utc).date().isoformat()

    with connect(db) as conn:
        scored = pd.read_sql_query(
            """
            SELECT u.*, c.value_flag, c.kelly_place_pct, c.ew_combined_ev
            FROM upcoming_runners u
            INNER JOIN card_scores c ON c.runner_id = u.runner_id
            WHERE u.card_date = ?
            """,
            conn,
            params=(card_date,),
        )

    gauges = evaluate_market_gauges()
    intents = build_execution_intents(scored, gauges=gauges) if not scored.empty else []
    if args.limit and args.limit > 0:
        intents = intents[: args.limit]

    report = route_execution_batch(intents, log_results=bool(args.log))
    summary = execution_summary()
    payload = {
        "platform": "racing",
        "ok": report.get("status") != "disabled" and report.get("errors", 0) == 0,
        "card_date": card_date,
        "intents": len(intents),
        "execution": report,
        "routing": summary,
        "cli_note": EXECUTION_DISABLED_MSG,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    print(json.dumps(payload))
    if report.get("status") == "disabled":
        return 0
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
