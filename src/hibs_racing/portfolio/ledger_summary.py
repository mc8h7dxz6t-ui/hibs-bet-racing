"""Forward paper ledger dimensions for ops monitoring (/api/portfolio/ledger-summary)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from hibs_racing.config import db_path, load_config
from hibs_racing.features.store import connect, init_db
from hibs_racing.place.paper_ledger import ledger_stats


def _value_pick_pnl(
    conn,
    *,
    days: int | None,
    backtest: bool,
) -> float:
    bt = 1 if backtest else 0
    if days is not None:
        from hibs_racing.place.paper_ledger import _date_cutoff

        cutoff = _date_cutoff(days)
        row = conn.execute(
            """
            SELECT COALESCE(SUM(result_pnl), 0)
            FROM paper_bets
            WHERE backtest = ? AND is_value_pick = 1
              AND status != 'open' AND created_at >= ?
            """,
            (bt, cutoff),
        ).fetchone()
    else:
        row = conn.execute(
            """
            SELECT COALESCE(SUM(result_pnl), 0)
            FROM paper_bets
            WHERE backtest = ? AND is_value_pick = 1 AND status != 'open'
            """,
            (bt,),
        ).fetchone()
    return round(float(row[0] or 0.0), 3)


def build_ledger_summary_payload(
    *,
    history_days: int | None = None,
    backtest: bool = False,
) -> dict[str, Any]:
    """Structured ledger totals — same source as tracker SQL baseline."""
    cfg = load_config()
    db = db_path(cfg)
    init_db(db)
    stats = ledger_stats(db, days=history_days, backtest=backtest)
    checked_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    try:
        with connect(db) as conn:
            value_pick_pnl = _value_pick_pnl(conn, days=history_days, backtest=backtest)
    except Exception as exc:
        return {
            "status": "error",
            "error": str(exc)[:200],
            "checked_at": checked_at,
        }

    total_pnl = round(float(stats.total_pnl), 2)
    return {
        "status": "ok",
        "ledger_kind": "backtest" if backtest else "forward",
        "history_days": history_days,
        "settled_rows": int(stats.settled_bets),
        "open_bets": int(stats.open_bets),
        "total_pnl": total_pnl,
        "value_pick_pnl": value_pick_pnl,
        "value_pick_count": int(stats.value_pick_count),
        "value_pick_settled": int(stats.value_pick_settled),
        "roi_pct": round(float(stats.roi_pct), 2) if stats.roi_pct is not None else None,
        "db_path": str(db),
        "checked_at": checked_at,
    }
