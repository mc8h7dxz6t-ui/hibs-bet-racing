"""Lightweight cross-sport portfolio summary for the unified top bar."""

from __future__ import annotations

from hibs_racing.portfolio.unified import build_unified_portfolio


def portfolio_summary_dict(*, football_days: int = 90) -> dict:
    payload = build_unified_portfolio(football_days=football_days, racing_limit=100)
    s = payload.get("summary") or {}
    racing_stats = payload.get("racing_stats") or {}
    return {
        "ok": payload.get("ok", True),
        "updated_at": payload.get("updated_at"),
        "combined_pnl_units": s.get("combined_pnl_units"),
        "football_pnl_units": s.get("football_pnl_units"),
        "racing_pnl_units": s.get("racing_pnl_units"),
        "football_settled": s.get("football_settled"),
        "racing_settled": s.get("racing_settled"),
        "football_open": max(0, (s.get("football_rows") or 0) - (s.get("football_settled") or 0)),
        "racing_open": racing_stats.get("open_bets", 0),
        "links": payload.get("links") or {},
    }
