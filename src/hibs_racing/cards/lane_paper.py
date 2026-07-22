"""Parallel paper lanes — production ledger stays on production; all gates logged side-by-side."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from hibs_racing.backtest.gate_benchmark import _apply_gate_flags
from hibs_racing.backtest.gate_impact import PARALLEL_FORWARD_LANES, apply_experimental_lanes, gate3_config
from hibs_racing.config import db_path, load_config
from hibs_racing.entity.natural_key import generate_natural_key
from hibs_racing.features.store import connect, init_db
from hibs_racing.place.paper_ledger import record_paper_bet


def attach_lane_flags(scored: pd.DataFrame) -> pd.DataFrame:
    """In-memory gate1..11 flags for refresh / smart picks (no DB write)."""
    if scored.empty:
        return scored
    cfg = load_config()
    paper = cfg.get("paper", {})
    out = scored.copy()
    if "flag_raw" not in out.columns and "value_flag" in out.columns:
        out["flag_raw"] = pd.to_numeric(out["value_flag"], errors="coerce").fillna(0).astype(int)
    gated = _apply_gate_flags(out, paper)
    for col in (
        "flag_none",
        "flag_gate1",
        "flag_gate2",
        "flag_production",
        "gate1_reason",
        "gate2_reason",
        "production_reason",
    ):
        if col in gated.columns:
            out[col] = gated[col]
    return apply_experimental_lanes(out, paper, full_cfg=cfg)


def _lane_picks(scored: pd.DataFrame, *, flag_col: str) -> pd.DataFrame:
    if scored.empty or flag_col not in scored.columns:
        return scored.iloc[0:0]
    return scored[pd.to_numeric(scored[flag_col], errors="coerce").fillna(0).astype(int) == 1]


def _parallel_forward_enabled(cfg: dict) -> bool:
    lanes_cfg = cfg.get("paper_lanes") or {}
    pf = lanes_cfg.get("parallel_forward") or {}
    if "enabled" in pf:
        return bool(pf.get("enabled"))
    anchor = lanes_cfg.get("gate3_anchor") or {}
    return bool(anchor.get("enabled", False))


def resolve_parallel_lane_specs(cfg: dict | None = None) -> list[tuple[str, str]]:
    """Return (lane_id, flag_col) pairs for forward parallel paper logging."""
    full = cfg if cfg is not None else load_config()
    if not _parallel_forward_enabled(full):
        return []
    pf = (full.get("paper_lanes") or {}).get("parallel_forward") or {}
    raw = pf.get("lanes")
    if isinstance(raw, list) and raw:
        specs: list[tuple[str, str]] = []
        for item in raw:
            if isinstance(item, str):
                lane = item.strip()
                if lane:
                    specs.append((lane, f"flag_{lane}"))
            elif isinstance(item, dict):
                lane = str(item.get("lane") or "").strip()
                flag_col = str(item.get("flag_col") or f"flag_{lane}").strip()
                if lane and flag_col:
                    specs.append((lane, flag_col))
        return specs
    anchor = (full.get("paper_lanes") or {}).get("gate3_anchor") or {}
    if anchor.get("enabled", False) and "lanes" not in pf:
        lane = str(anchor.get("lane") or "gate3")
        flag_col = str(anchor.get("flag_col") or f"flag_{lane}")
        return [(lane, flag_col)]
    return [(lane, f"flag_{lane}") for lane in PARALLEL_FORWARD_LANES]


def _bet_context_from_rec(rec: dict, *, card_date: str) -> dict[str, str | None]:
    cd = rec.get("card_date") or card_date
    course = rec.get("course")
    off_time = rec.get("off_time")
    horse_name = rec.get("horse_name")
    race_natural_key = rec.get("race_natural_key")
    if not race_natural_key and cd and course and off_time:
        race_natural_key = generate_natural_key(str(cd), str(course), str(off_time))
    return {
        "card_date": str(cd) if cd else None,
        "course": str(course) if course else None,
        "off_time": str(off_time) if off_time else None,
        "horse_name": str(horse_name) if horse_name else None,
        "race_natural_key": str(race_natural_key) if race_natural_key else None,
    }


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
    Log parallel lane picks without disturbing production reconciliation.
    Dedupes on (runner_id, paper_lane) for open/live value picks on card_date.
    """
    cfg = load_config()
    if not _parallel_forward_enabled(cfg):
        return {"lane": lane, "logged": 0, "skipped": "disabled"}
    specs = resolve_parallel_lane_specs(cfg)
    if specs and not any(s_lane == lane and s_flag == flag_col for s_lane, s_flag in specs):
        return {"lane": lane, "logged": 0, "skipped": "lane_not_configured"}

    db = database or db_path(cfg)
    paper = cfg.get("paper", {})
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
        ctx = _bet_context_from_rec(rec, card_date=card_date)
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
            card_date=ctx.get("card_date"),
            course=ctx.get("course"),
            off_time=ctx.get("off_time"),
            horse_name=ctx.get("horse_name"),
            race_natural_key=ctx.get("race_natural_key"),
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
    }


def sync_parallel_lane_ledgers(
    scored: pd.DataFrame,
    *,
    card_date: str,
    database: Path | None = None,
    stake: float | None = None,
    manifest_id: str | None = None,
    odds_source: str | None = None,
    engine_profile: dict | None = None,
) -> list[dict]:
    """Log all configured parallel forward lanes for one card date."""
    cfg = load_config()
    specs = resolve_parallel_lane_specs(cfg)
    if not specs:
        return []
    results: list[dict] = []
    for lane, flag_col in specs:
        results.append(
            sync_lane_paper_ledger(
                scored,
                card_date=card_date,
                lane=lane,
                flag_col=flag_col,
                database=database,
                stake=stake,
                manifest_id=manifest_id,
                odds_source=odds_source,
                engine_profile=engine_profile,
            )
        )
    return results


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
