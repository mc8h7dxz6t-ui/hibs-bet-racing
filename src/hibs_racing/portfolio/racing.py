"""Racing-only paper ledger portfolio (analytics product — no cross-sport deps)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from hibs_racing.place.public_tracker import build_public_tracker_dict


def _normalize_racing_row(row: dict) -> dict[str, Any]:
    status = row.get("status") or "open"
    pnl = float(row["result_pnl"]) if row.get("result_pnl") is not None and status != "open" else None
    result = "pending"
    if status in ("won", "placed"):
        result = "W"
    elif status == "lost":
        result = "L"
    event_at = f"{row.get('card_date') or ''}T{row.get('off_time') or '00:00'}:00"
    edge_pct = None
    if row.get("model_ev") is not None:
        try:
            edge_pct = float(row["model_ev"]) * 100
        except (TypeError, ValueError):
            edge_pct = None
    return {
        "source": "hibs-racing",
        "sport": "racing",
        "id": row.get("bet_id"),
        "event_at": event_at,
        "settled_at": row.get("settled_at"),
        "description": f"{row.get('horse_name')} @ {row.get('course')}",
        "league_or_meeting": row.get("course"),
        "selection": row.get("bet_type"),
        "odds": row.get("offered_win"),
        "stake": row.get("stake_units"),
        "result": result,
        "pnl": pnl,
        "edge_pct": edge_pct,
        "clv_pp": None,
        "cohort": "paper",
        "meta": {
            "race_id": row.get("race_id"),
            "runner_id": row.get("runner_id"),
            "is_value_pick": bool(row.get("is_value_pick")),
            "finish_pos": row.get("finish_pos"),
            "verification_hash": row.get("verification_hash"),
        },
    }


def build_racing_portfolio(*, racing_limit: int = 200, history_days: int | None = None) -> dict[str, Any]:
    """Paper ledger summary for /portfolio and API consumers."""
    tracker = build_public_tracker_dict(limit=racing_limit, history_days=history_days)
    racing_rows = [_normalize_racing_row(r) for r in tracker.get("ledger_rows") or []]
    racing_stats = tracker.get("stats") or {}
    # Headline P&L = forward value picks only (matches bankroll / truth_plane cohort).
    rc_pnl = racing_stats.get("value_pick_pnl")
    if rc_pnl is None:
        rc_pnl = racing_stats.get("total_pnl")
    if rc_pnl is None:
        rc_pnl = sum(r["pnl"] for r in racing_rows if r.get("pnl") is not None and (r.get("meta") or {}).get("is_value_pick"))
    rc_settled = racing_stats.get("value_pick_settled")
    if rc_settled is None:
        rc_settled = racing_stats.get("settled_bets")
    if rc_settled is None:
        rc_settled = sum(1 for r in racing_rows if r.get("pnl") is not None)

    return {
        "ok": True,
        "mode": "analytics",
        "updated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "history_days": tracker.get("history_days"),
        "racing_stats": racing_stats,
        "clv": tracker.get("clv"),
        "pnl_plane": "forward_value_picks",
        "summary": {
            "total_rows": len(racing_rows),
            "racing_rows": len(racing_rows),
            "racing_pnl_units": round(float(rc_pnl), 2),
            "combined_pnl_units": round(float(rc_pnl), 2),
            "all_paper_pnl_units": round(float(racing_stats.get("total_pnl") or 0), 2),
            "racing_settled": int(rc_settled or 0),
            "open_bets": racing_stats.get("value_pick_open", racing_stats.get("open_bets", 0)),
            "value_pick_open": racing_stats.get("value_pick_open"),
            "value_pick_count": racing_stats.get("value_pick_count"),
        },
        "ledger": racing_rows,
        "links": {
            "racing_tracker": "/tracker",
            "csv_export": tracker.get("export_urls", {}).get("csv", "/api/tracker/export.csv"),
        },
    }
