"""Exchange place EV rollout status (coverage + settled sample)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from hibs_racing.config import db_path, load_config
from hibs_racing.features.store import connect, init_db
from hibs_racing.place.exchange_config import exchange_runtime_config


def exchange_ev_status(*, database: Path | None = None) -> dict:
    cfg = load_config()
    paper = cfg.get("paper", {})
    runtime = exchange_runtime_config(paper)
    db = database or db_path(cfg)
    init_db(db)

    coverage_pct = None
    priced_n = 0
    total_n = 0
    with connect(db) as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS n,
                   SUM(CASE WHEN place_ev_exchange IS NOT NULL THEN 1 ELSE 0 END) AS priced
            FROM card_scores
            """
        ).fetchone()
        if row:
            total_n = int(row[0] or 0)
            priced_n = int(row[1] or 0)
            coverage_pct = round(100.0 * priced_n / total_n, 2) if total_n else 0.0

        settled_row = conn.execute(
            """
            SELECT COUNT(*) FROM paper_bets
            WHERE backtest = 0 AND is_value_pick = 1
              AND COALESCE(paper_lane, 'production') = 'gate3'
              AND status IN ('won', 'lost', 'placed')
            """
        ).fetchone()
        settled_exchange = int(settled_row[0] or 0) if settled_row else 0

    min_cov = float(runtime["exchange_ev_min_coverage_pct"])
    min_settled = int(runtime["exchange_ev_min_settled"])
    unlock = (
        coverage_pct is not None
        and coverage_pct >= min_cov
        and settled_exchange >= min_settled
    )

    return {
        "exchange_ev_shadow": runtime["exchange_ev_shadow"],
        "exchange_ev_production": runtime["exchange_ev_production"],
        "exchange_commission": runtime["exchange_commission"],
        "kelly_fraction": runtime["kelly_fraction"],
        "max_runner_risk_pct": runtime["max_runner_risk_pct"],
        "scored_runners": total_n,
        "exchange_priced_runners": priced_n,
        "exchange_place_coverage_pct": coverage_pct,
        "settled_exchange_picks": settled_exchange,
        "min_coverage_pct": min_cov,
        "min_settled_picks": min_settled,
        "production_unlock_recommended": unlock,
        "production_flip_env": "HIBS_EXCHANGE_EV_PRODUCTION=1",
        "message": (
            "Ready for operator production flip"
            if unlock
            else f"Shadow mode — need coverage>={min_cov}% and settled>={min_settled}"
        ),
    }
