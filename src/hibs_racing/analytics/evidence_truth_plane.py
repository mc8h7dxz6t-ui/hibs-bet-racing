"""Unified ROI / calibration truth plane — one reconciled view for diligence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from hibs_racing.config import ROOT, db_path, load_config
from hibs_racing.features.store import connect, init_db
from hibs_racing.place.paper_ledger import ledger_stats


def _load_production_benchmark() -> dict[str, Any] | None:
    path = ROOT / "exports" / "production_benchmark_90d.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _forward_lane_stats(*, days: int = 90, lane: str | None = None) -> dict[str, Any]:
    """Forward paper stats; optional lane filter via ledger_events audit payload."""
    cfg = load_config()
    db = db_path(cfg)
    init_db(db)
    base = ledger_stats(db, days=days, backtest=False).to_dict()
    if not lane or lane == "production":
        return {**base, "lane": "production"}
    try:
        with connect(db) as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS n,
                       SUM(CASE WHEN pb.status != 'open' THEN 1 ELSE 0 END) AS settled,
                       SUM(CASE WHEN pb.status != 'open' THEN pb.result_pnl ELSE 0 END) AS pnl,
                       SUM(CASE WHEN pb.status != 'open' THEN pb.stake_units ELSE 0 END) AS staked
                FROM paper_bets pb
                WHERE pb.backtest = 0 AND pb.is_value_pick = 1
                  AND COALESCE(pb.paper_lane, 'production') = ?
                  AND pb.created_at >= date('now', ?)
                """,
                (lane, f"-{int(days)} days"),
            ).fetchone()
        if not row or int(row[0] or 0) == 0:
            return {"lane": lane, "n_rows": 0, "settled": 0, "roi_pct": None, "total_pnl": 0.0}
        settled = int(row[1] or 0)
        pnl = float(row[2] or 0)
        staked = float(row[3] or 0)
        roi = (100.0 * pnl / staked) if staked > 0 else None
        return {
            "lane": lane,
            "n_rows": int(row[0]),
            "settled": settled,
            "total_pnl": round(pnl, 2),
            "roi_pct": round(roi, 2) if roi is not None else None,
        }
    except Exception:
        return {**base, "lane": lane}


def build_evidence_truth_plane(
    *,
    health: dict[str, Any] | None = None,
    days: int = 90,
) -> dict[str, Any]:
    """
    Reconcile marketing holdout, snapshot replay benchmark, and forward paper ledger.

    Settlement modes:
      - sp_backtest: holdout replay at starting price (calibration anchor)
      - sp_snapshot_90d: rolling snapshot gate replay at SP
      - forward_offered: live paper at bet-time offered odds (default)
      - forward_sp: when HIBS_RACING_SETTLE_AT_SP=1
    """
    cfg = load_config()
    bt = cfg.get("backtest") or {}
    benchmark = _load_production_benchmark()
    from hibs_racing.analytics.backtest_results import backtest_results_summary

    results = backtest_results_summary(days=days)
    settle_at_sp = __import__("os").environ.get("HIBS_RACING_SETTLE_AT_SP", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    forward_mode = "forward_sp" if settle_at_sp else "forward_offered"

    reliability = (health or {}).get("reliability") or {}
    place_rel = (health or {}).get("place_reliability") or {}

    planes: list[dict[str, Any]] = []

    if results.get("backtest"):
        bt_stats = results["backtest"]
        planes.append(
            {
                "id": "sp_backtest_holdout",
                "label": "SP holdout backtest (paper ledger)",
                "settlement": "starting_price",
                "window": f"OOS from {bt.get('test_start', '2026-05-01')}",
                "roi_pct": bt_stats.get("roi_pct"),
                "settled": bt_stats.get("settled_bets"),
                "strike_rate": bt_stats.get("strike_rate"),
                "use_for": "calibration_anchor",
                "caveat": "SP settlement — optimistic vs morning exchange prices.",
            }
        )

    if benchmark:
        g2 = benchmark.get("gate2") or benchmark.get("production") or {}
        planes.append(
            {
                "id": "sp_snapshot_gate2_90d",
                "label": "Snapshot replay Gate2 (90d)",
                "settlement": "starting_price",
                "window": f"{benchmark.get('start')} → {benchmark.get('end')}",
                "roi_pct": g2.get("roi_pct"),
                "settled": g2.get("settled"),
                "hit_rate": g2.get("hit_rate"),
                "use_for": "gate_regression_internal",
                "caveat": "Same gate config as production; steam/DQ may differ in live batch.",
            }
        )
        none_lane = benchmark.get("none") or {}
        planes.append(
            {
                "id": "sp_snapshot_raw_ev_90d",
                "label": "Raw EV (no gates) — 90d snapshot",
                "settlement": "starting_price",
                "window": f"{benchmark.get('start')} → {benchmark.get('end')}",
                "roi_pct": none_lane.get("roi_pct"),
                "settled": none_lane.get("settled"),
                "use_for": "gate_value_proof",
                "caveat": "Proves gates are the edge — raw ranker+EV alone is negative.",
            }
        )

    fwd = results.get("forward") or {}
    planes.append(
        {
            "id": forward_mode,
            "label": "Forward paper (production lane)",
            "settlement": "starting_price" if settle_at_sp else "offered_at_bet_time",
            "window": f"rolling {days}d",
            "roi_pct": fwd.get("roi_pct"),
            "settled": fwd.get("settled_bets"),
            "strike_rate": fwd.get("strike_rate"),
            "use_for": "live_proof_primary",
            "caveat": None if not settle_at_sp else "HIBS_RACING_SETTLE_AT_SP=1 — SP not exchange-verified.",
        }
    )

    gate3_fwd = _forward_lane_stats(days=days, lane="gate3")
    if int(gate3_fwd.get("n_rows") or 0) > 0:
        planes.append(
            {
                "id": "forward_gate3_anchor",
                "label": "Forward paper (Gate3 anchor lane)",
                "settlement": "offered_at_bet_time",
                "window": f"rolling {days}d",
                "roi_pct": gate3_fwd.get("roi_pct"),
                "settled": gate3_fwd.get("settled"),
                "use_for": "promotion_trial",
                "caveat": "Parallel anchor lane — not live production scoring.",
            }
        )

    primary_roi = None
    for p in planes:
        if p["id"] == forward_mode:
            primary_roi = p.get("roi_pct")
            break

    return {
        "primary_settlement_mode": forward_mode,
        "settle_at_sp": settle_at_sp,
        "planes": planes,
        "calibration": {
            # settled_paper_calibration() exposes brier_score, not brier
            "win_brier": reliability.get("brier_score", reliability.get("brier")),
            "place_brier": place_rel.get("brier"),
            "place_mce": place_rel.get("mean_calibration_error"),
            "place_n": place_rel.get("n"),
            "win_n": reliability.get("n"),
        },
        "settlement_price_mix": results.get("settlement_price_mix"),
        "roi_disclaimer": results.get("roi_disclaimer"),
        "oos_holdout_start": results.get("oos_holdout_start"),
        "headline_forward_roi_pct": primary_roi,
        "reconciliation_note": (
            "Marketing SP holdout ROI and internal 90d Gate2 snapshot ROI use different "
            "windows and methods — compare only within the same plane row."
        ),
    }
