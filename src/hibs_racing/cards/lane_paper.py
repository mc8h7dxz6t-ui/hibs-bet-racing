"""Parallel paper lanes (Gate3 anchor) — production ledger stays on production lane."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from hibs_racing.backtest.gate_impact import apply_experimental_lanes, gate3_config
from hibs_racing.config import db_path, load_config
from hibs_racing.features.store import connect, init_db
from hibs_racing.place.paper_ledger import record_paper_bet


def attach_lane_flags(scored: pd.DataFrame) -> pd.DataFrame:
    """In-memory Gate3..8 flags for refresh / smart picks (no DB write)."""
    if scored.empty:
        return scored
    cfg = load_config()
    paper = cfg.get("paper", {})
    return apply_experimental_lanes(scored, paper, full_cfg=cfg)


def _lane_picks(scored: pd.DataFrame, *, flag_col: str) -> pd.DataFrame:
    if scored.empty or flag_col not in scored.columns:
        return scored.iloc[0:0]
    return scored[pd.to_numeric(scored[flag_col], errors="coerce").fillna(0).astype(int) == 1]


def sync_lane_paper_ledger(
    scored: pd.DataFrame,
    *,
    card_date: str,
    lane: str = "gate3",
    flag_col: str = "flag_gate3",
    database: Path | None = None,
    stake: float | None = None,
    manifest_id: str | None = None,
    odds_source: str | None = None,
    engine_profile: dict | None = None,
) -> dict:
    """
    Log parallel anchor-lane picks without disturbing production reconciliation.
    Dedupes on (runner_id, paper_lane) for open/live value picks on card_date.
    """
    cfg = load_config()
    paper = cfg.get("paper", {})
    anchor_cfg = (cfg.get("paper_lanes") or {}).get("gate3_anchor") or {}
    if not anchor_cfg.get("enabled", True):
        return {"lane": lane, "logged": 0, "skipped": "disabled"}

    db = database or db_path(cfg)
    init_db(db)
    stake_f = float(stake if stake is not None else paper.get("default_stake", 1.0))
    picks = _lane_picks(scored, flag_col=flag_col)
    logged = 0
    skipped_dup = 0
    for rec in picks.to_dict(orient="records"):
        rid = str(rec.get("runner_id") or "")
        if not rid:
            continue
        with connect(db) as conn:
            existing = conn.execute(
                """
                SELECT bet_id FROM paper_bets
                WHERE runner_id = ? AND backtest = 0 AND is_value_pick = 1
                  AND COALESCE(paper_lane, 'production') = ?
                  AND (card_date = ? OR created_at LIKE ?)
                LIMIT 1
                """,
                (rid, lane, card_date, f"{card_date}%"),
            ).fetchone()
        if existing:
            skipped_dup += 1
            continue
        record_paper_bet(
            rec["race_id"],
            rid,
            "each_way",
            stake_f,
            model_ev=rec.get("ew_combined_ev"),
            offered_win=rec.get("win_decimal"),
            place_terms=f"1/{int((rec.get('place_fraction') or 0.25)*4)} top {int(rec.get('places') or 3)}",
            is_value_pick=True,
            backtest=False,
            paper_lane=lane,
            audit_extra={
                "paper_lane": lane,
                "lane_flag": flag_col,
                "odds_source": odds_source or rec.get("odds_source"),
                "data_quality_pct": rec.get("data_quality_pct"),
                "steam_gate": rec.get("steam_gate"),
                "value_gate_reason": rec.get("value_gate_reason"),
                "engine_profile": engine_profile,
                "manifest_id": manifest_id,
            },
        )
        logged += 1
    return {
        "lane": lane,
        "flag_col": flag_col,
        "expected": len(picks),
        "logged": logged,
        "skipped_duplicate": skipped_dup,
        "gate3_config_note": "Conservative anchor — tighter OR/confidence/caps vs production.",
    }


def gate3_lane_config_summary() -> dict:
    cfg = load_config()
    paper = cfg.get("paper", {})
    g3 = gate3_config(paper, full_cfg=cfg)
    g2 = g3.get("gate2") or {}
    return {
        "lane": "gate3",
        "min_official_rating": g3.get("min_official_rating"),
        "min_trainer_rtf": g3.get("min_trainer_rtf"),
        "min_confidence": g2.get("min_confidence"),
        "min_stressed_place_ev": g2.get("min_stressed_place_ev"),
        "max_value_per_race": g2.get("max_value_per_race"),
        "max_value_per_meeting": g2.get("max_value_per_meeting"),
    }
