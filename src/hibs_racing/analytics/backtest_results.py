"""Racing backtest + forward results for health and tracker transparency."""

from __future__ import annotations

from typing import Any

from hibs_racing.config import db_path, load_config
from hibs_racing.features.store import connect, init_db
from hibs_racing.place.paper_ledger import ledger_stats


def backtest_results_summary(*, days: int = 90) -> dict[str, Any]:
    """Forward vs backtest paper ledger + settlement price mix (offered vs SP)."""
    cfg = load_config()
    db = db_path(cfg)
    init_db(db)
    forward = ledger_stats(db, days=days, backtest=False).to_dict()
    backtest = ledger_stats(db, days=None, backtest=True).to_dict()
    settlement_mix = {"offered": 0, "sp": 0, "unknown": 0}
    try:
        with connect(db) as conn:
            rows = conn.execute(
                """
                SELECT settlement_price_source, COUNT(*) AS n
                FROM paper_bets
                WHERE status != 'open' AND backtest = 0
                GROUP BY settlement_price_source
                """
            ).fetchall()
            for src, n in rows:
                key = str(src or "offered").lower()
                if key in settlement_mix:
                    settlement_mix[key] += int(n)
                else:
                    settlement_mix["unknown"] += int(n)
    except Exception:
        pass
    return {
        "forward": forward,
        "backtest": backtest,
        "settlement_price_mix": settlement_mix,
        "roi_disclaimer": (
            "Forward ROI uses offered exchange/win prices at bet time unless HIBS_RACING_SETTLE_AT_SP=1. "
            "Backtest ROI is SP-based holdout — not live exchange-verified."
        ),
        "oos_holdout_start": (cfg.get("backtest") or {}).get("test_start", "2026-05-01"),
    }
