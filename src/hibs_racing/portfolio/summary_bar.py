"""Racing paper-ledger summary for the top bar."""

from __future__ import annotations

from hibs_racing.portfolio.racing import build_racing_portfolio


def portfolio_summary_dict(*, history_days: int | None = None) -> dict:
    payload = build_racing_portfolio(racing_limit=100, history_days=history_days)
    s = payload.get("summary") or {}
    racing_stats = payload.get("racing_stats") or {}
    pnl = s.get("racing_pnl_units")
    return {
        "ok": payload.get("ok", True),
        "mode": "analytics",
        "updated_at": payload.get("updated_at"),
        "combined_pnl_units": pnl,
        "racing_pnl_units": pnl,
        "racing_settled": s.get("racing_settled"),
        "racing_open": racing_stats.get("open_bets", 0),
        "links": payload.get("links") or {},
    }
