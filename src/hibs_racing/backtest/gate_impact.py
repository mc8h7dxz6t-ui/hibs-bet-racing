"""Marginal ROI per gate block reason + in-memory Gate3–8 experimental replay lanes."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from hibs_racing.backtest.gate_benchmark import (
    _apply_gate_flags,
    _delta,
    _historical_bounds,
    _month_periods,
    _settle,
)
from hibs_racing.backtest.snapshot_store import load_snapshots, resolve_snapshot_config_hash
from hibs_racing.cards.actionability import _gate2_confidence, apply_value_gates
from hibs_racing.config import db_path, load_config

EXPERIMENTAL_LANES: tuple[str, ...] = ("gate3", "gate4", "gate5", "gate6", "gate7")
WALKFORWARD_FOCUS_LANES: tuple[str, ...] = ("gate2", "gate3", "gate5", "gate6", "gate7", "gate8")

_G2_FLAT_KEYS: frozenset[str] = frozenset(
    {
        "min_confidence",
        "min_stressed_place_ev",
        "max_value_per_race",
        "max_value_per_meeting",
        "min_win_decimal",
        "max_win_decimal",
        "min_place_ev_medium",
        "min_place_ev_small",
        "min_place_ev_large",
    }
)


def _replay_base(paper_cfg: dict) -> dict:
    cfg = deepcopy(paper_cfg)
    cfg["enforce_steam_gate"] = False
    cfg["min_data_quality_pct"] = None
    return cfg


def _normalize_lane_spec(lane_spec: dict) -> dict:
    """Map flat YAML keys (min_confidence, caps, …) into gate2 block."""
    out: dict[str, Any] = {}
    g2 = dict(lane_spec.get("gate2") or {}) if isinstance(lane_spec.get("gate2"), dict) else {}
    for key, val in lane_spec.items():
        if key in ("min_official_rating", "min_trainer_rtf", "base_lane"):
            out[key] = val
        elif key in _G2_FLAT_KEYS:
            g2[key] = val
    if g2:
        out["gate2"] = g2
    return out


def _merge_lane_spec(cfg: dict, lane_spec: dict) -> dict:
    out = deepcopy(cfg)
    norm = _normalize_lane_spec(lane_spec)
    if norm.get("min_official_rating") is not None:
        out["min_official_rating"] = int(norm["min_official_rating"])
    if norm.get("min_trainer_rtf") is not None:
        out["min_trainer_rtf"] = float(norm["min_trainer_rtf"])
    g2 = out.setdefault("gate2", {})
    if not isinstance(g2, dict):
        g2 = {}
        out["gate2"] = g2
    g2["enabled"] = True
    g2spec = norm.get("gate2")
    if isinstance(g2spec, dict):
        g2.update(g2spec)
    return out


def _lane_spec(full_cfg: dict, yaml_key: str) -> dict | None:
    block = full_cfg.get("experimental_replay_lanes", {})
    if not isinstance(block, dict):
        return None
    spec = block.get(yaml_key)
    return spec if isinstance(spec, dict) else None


def gate3_config(paper_cfg: dict, full_cfg: dict | None = None) -> dict:
    """Conservative core lane — tighter OR, confidence, caps, cold-trainer block."""
    cfg = _replay_base(paper_cfg)
    cfg["min_official_rating"] = max(int(cfg.get("min_official_rating") or 45), 50)
    cfg["min_trainer_rtf"] = cfg.get("min_trainer_rtf") or 10
    g2 = cfg.setdefault("gate2", {})
    if isinstance(g2, dict):
        g2.update(
            {
                "enabled": True,
                "min_confidence": max(float(g2.get("min_confidence", 0.55)), 0.60),
                "min_stressed_place_ev": max(float(g2.get("min_stressed_place_ev", 0.0)), 0.02),
                "max_value_per_race": min(int(g2.get("max_value_per_race") or 3), 2),
                "max_value_per_meeting": min(int(g2.get("max_value_per_meeting") or 6), 4),
            }
        )
    return cfg


def gate4_config(paper_cfg: dict, full_cfg: dict | None = None) -> dict:
    """Expansion lane — looser caps and regime EV floor; same OR/suitability."""
    cfg = _replay_base(paper_cfg)
    g2 = cfg.setdefault("gate2", {})
    if isinstance(g2, dict):
        g2.update(
            {
                "enabled": True,
                "min_confidence": min(float(g2.get("min_confidence", 0.55)), 0.50),
                "max_value_per_race": max(int(g2.get("max_value_per_race") or 3), 4),
                "max_value_per_meeting": max(int(g2.get("max_value_per_meeting") or 6), 8),
                "min_place_ev_medium": min(float(g2.get("min_place_ev_medium", 0.05)), 0.045),
            }
        )
    return cfg


def gate5_config(paper_cfg: dict, full_cfg: dict | None = None) -> dict:
    """Sniper lane — tighter Gate3 (replay only; superseded by Gate7 for true sniper)."""
    spec = _lane_spec(full_cfg or {}, "gate5_sniper")
    if spec:
        return _merge_lane_spec(gate3_config(paper_cfg, full_cfg), spec)
    cfg = gate3_config(paper_cfg, full_cfg)
    cfg["min_official_rating"] = max(int(cfg.get("min_official_rating") or 50), 60)
    cfg["min_trainer_rtf"] = 15
    g2 = cfg.setdefault("gate2", {})
    if isinstance(g2, dict):
        g2.update(
            {
                "min_confidence": 0.65,
                "min_stressed_place_ev": 0.05,
                "max_value_per_race": 1,
                "max_value_per_meeting": 2,
            }
        )
    return cfg


def gate6_config(paper_cfg: dict, full_cfg: dict | None = None) -> dict:
    """Market-resilient lane — Gate3 strictness + explicit SP band (replay only)."""
    spec = _lane_spec(full_cfg or {}, "gate6_market_bounded")
    if spec:
        return _merge_lane_spec(gate3_config(paper_cfg, full_cfg), spec)
    cfg = gate3_config(paper_cfg, full_cfg)
    g2 = cfg.setdefault("gate2", {})
    if isinstance(g2, dict):
        g2.update(
            {
                "min_win_decimal": 2.0,
                "max_win_decimal": 10.0,
            }
        )
    return cfg


def gate7_config(paper_cfg: dict, full_cfg: dict | None = None) -> dict:
    """True sniper — Gate3 core + extreme OR/RTF/caps (replay only)."""
    spec = _lane_spec(full_cfg or {}, "gate7_true_sniper")
    if spec:
        return _merge_lane_spec(gate3_config(paper_cfg, full_cfg), spec)
    cfg = gate3_config(paper_cfg, full_cfg)
    cfg["min_official_rating"] = 65
    cfg["min_trainer_rtf"] = 20
    g2 = cfg.setdefault("gate2", {})
    if isinstance(g2, dict):
        g2.update(
            {
                "min_confidence": 0.65,
                "min_stressed_place_ev": 0.05,
                "max_value_per_race": 1,
                "max_value_per_meeting": 1,
            }
        )
    return cfg


def _rank_col(frame: pd.DataFrame) -> str:
    if "ew_combined_ev" in frame.columns:
        return "ew_combined_ev"
    if "place_ev" in frame.columns:
        return "place_ev"
    return "combo_bayes_place"


def _apply_gate8_regime_blend(frame: pd.DataFrame, paper_cfg: dict, full_cfg: dict) -> pd.DataFrame:
    """Gate8: Gate3 baseline with tiered caps — tighter when confidence exceeds trigger."""
    spec = _lane_spec(full_cfg, "gate8_regime_blend") or {}
    trigger = float(spec.get("trigger_confidence", 0.70))
    default_race = int(spec.get("default_max_value_per_race", 2))
    default_meeting = int(spec.get("default_max_value_per_meeting", 4))
    escalated_race = int(spec.get("escalated_max_value_per_race", 1))
    escalated_meeting = int(spec.get("escalated_max_value_per_meeting", 2))

    g3 = gate3_config(paper_cfg, full_cfg)
    g2 = g3.setdefault("gate2", {})
    if isinstance(g2, dict):
        g2["max_value_per_race"] = None
        g2["max_value_per_meeting"] = None

    out = _apply_lane_from_none(frame, g3, "_gate8_precap", "gate8_reason")
    rank = _rank_col(out)
    flags = pd.Series(0, index=out.index, dtype=int)
    race_counts: dict[str, int] = {}
    meeting_counts: dict[tuple[str, str], int] = {}

    candidates = out[out["_gate8_precap"].eq(1)].copy()
    if not candidates.empty:
        candidates = candidates.sort_values([rank], ascending=False, na_position="last")
        for idx, row in candidates.iterrows():
            conf = _gate2_confidence(row, g3)
            max_r = escalated_race if conf >= trigger else default_race
            max_m = escalated_meeting if conf >= trigger else default_meeting
            race_id = str(row.get("race_id", ""))
            meeting_key = (str(row.get("card_date", "")), str(row.get("course", "")))
            if race_counts.get(race_id, 0) >= max_r:
                continue
            if meeting_counts.get(meeting_key, 0) >= max_m:
                continue
            flags.loc[idx] = 1
            race_counts[race_id] = race_counts.get(race_id, 0) + 1
            meeting_counts[meeting_key] = meeting_counts.get(meeting_key, 0) + 1

    out["flag_gate8"] = flags.astype(int)
    out.loc[out["flag_gate8"].eq(0) & out["_gate8_precap"].eq(1), "gate8_reason"] = "gate8_tier_cap"
    out.loc[out["flag_gate8"].eq(1), "gate8_reason"] = None
    return out.drop(columns=["_gate8_precap"], errors="ignore")


def _lane_config_builders(full_cfg: dict) -> dict[str, Any]:
    paper = full_cfg.get("paper", {})
    return {
        "gate3": lambda: gate3_config(paper, full_cfg),
        "gate4": lambda: gate4_config(paper, full_cfg),
        "gate5": lambda: gate5_config(paper, full_cfg),
        "gate6": lambda: gate6_config(paper, full_cfg),
        "gate7": lambda: gate7_config(paper, full_cfg),
    }


def _apply_lane_from_none(frame: pd.DataFrame, paper_cfg: dict, flag_col: str, reason_col: str) -> pd.DataFrame:
    out = frame.copy()
    if "flag_none" not in out.columns:
        out["flag_none"] = pd.to_numeric(out["flag_raw"], errors="coerce").fillna(0).astype(int)
    lane_in = out.copy()
    lane_in["value_flag"] = lane_in["flag_none"]
    lane_in = lane_in.drop(columns=["value_gate_reason"], errors="ignore")
    gated = apply_value_gates(lane_in, paper_cfg)
    out[flag_col] = pd.to_numeric(gated["value_flag"], errors="coerce").fillna(0).astype(int)
    out[reason_col] = gated.get("value_gate_reason")
    return out


def apply_experimental_lanes(frame: pd.DataFrame, paper_cfg: dict, full_cfg: dict | None = None) -> pd.DataFrame:
    """Attach flag_gate3..8 in-memory via standard value-gate pipeline (no DB write)."""
    merged_cfg = full_cfg if full_cfg is not None else {"paper": paper_cfg}
    builders = _lane_config_builders(merged_cfg)

    out = frame.copy()
    for lane in EXPERIMENTAL_LANES:
        out = _apply_lane_from_none(out, builders[lane](), f"flag_{lane}", f"{lane}_reason")
    out = _apply_gate8_regime_blend(out, paper_cfg, merged_cfg)
    return out


def _experimental_lane_stats(frame: pd.DataFrame) -> dict[str, dict]:
    stats = {
        "gate2": _settle(frame, "flag_gate2"),
        "production": _settle(frame, "flag_production"),
    }
    for lane in (*EXPERIMENTAL_LANES, "gate8"):
        stats[lane] = _settle(frame, f"flag_{lane}")
    return stats


def _promotion_criteria(full_cfg: dict) -> dict:
    block = full_cfg.get("experimental_replay_lanes", {})
    raw = block.get("promotion_criteria", {}) if isinstance(block, dict) else {}
    if not isinstance(raw, dict):
        raw = {}
    return {
        "min_picks_per_month_gate5": int(raw.get("min_picks_per_month_gate5", 15)),
        "min_aggregate_roi_pct": float(raw.get("min_aggregate_roi_pct", 10.0)),
        "min_months_beat_gate2": int(raw.get("min_months_beat_gate2", 6)),
        "min_months_beat_gate3": int(raw.get("min_months_beat_gate3", 6)),
    }


def _monthly_roi_wins(period_rows: list[dict], lane: str, *, vs: str) -> int:
    wins = 0
    for row in period_rows:
        a = row.get(lane, {})
        b = row.get(vs, {})
        if int(a.get("picks") or 0) <= 0:
            continue
        ar, br = a.get("roi_pct"), b.get("roi_pct")
        if ar is not None and br is not None and ar > br:
            wins += 1
    return wins


def evaluate_lane_promotion(
    *,
    aggregate: dict,
    period_rows: list[dict],
    months_with_data: int,
    full_cfg: dict,
) -> dict:
    """Institutional promotion gate — replay only until all checks pass."""
    crit = _promotion_criteria(full_cfg)
    out: dict[str, dict] = {}

    def _lane_eval(lane: str, *, volume_floor: bool, vs_gate3_required: bool) -> dict:
        stats = aggregate.get(lane, {})
        picks = int(stats.get("picks") or 0)
        roi = stats.get("roi_pct")
        avg_monthly = (picks / months_with_data) if months_with_data else 0.0
        beat_g2 = _monthly_roi_wins(period_rows, lane, vs="gate2")
        beat_g3 = _monthly_roi_wins(period_rows, lane, vs="gate3")
        g3_roi = aggregate.get("gate3", {}).get("roi_pct")
        volume_ok = avg_monthly >= crit["min_picks_per_month_gate5"] if volume_floor else True
        roi_ok = isinstance(roi, (int, float)) and float(roi) >= crit["min_aggregate_roi_pct"]
        beats_g3_agg = (
            isinstance(roi, (int, float))
            and isinstance(g3_roi, (int, float))
            and float(roi) > float(g3_roi)
        )
        months_g2_ok = beat_g2 >= crit["min_months_beat_gate2"]
        months_g3_ok = beat_g3 >= crit["min_months_beat_gate3"]
        sniper_too_thin = volume_floor and avg_monthly < crit["min_picks_per_month_gate5"]
        promotion_ready = bool(
            volume_ok
            and roi_ok
            and months_g2_ok
            and (months_g3_ok if vs_gate3_required else True)
            and (beats_g3_agg if vs_gate3_required else True)
        )
        note = "Replay-only until scoring hash stable + slippage sample >= 300."
        if sniper_too_thin:
            note = (
                "Volume below sniper floor — cannot build reliable edge on thin pool; "
                "focus on ranker fix, not tighter gates."
            )
        return {
            "aggregate_roi_pct": roi,
            "total_picks": picks,
            "avg_picks_per_dense_month": round(avg_monthly, 1),
            "volume_floor_pass": volume_ok,
            "sniper_too_thin": sniper_too_thin,
            "aggregate_roi_pass": roi_ok,
            "beats_gate3_aggregate": beats_g3_agg,
            "months_beat_gate2": beat_g2,
            "months_beat_gate3": beat_g3,
            "months_beat_gate2_pass": months_g2_ok,
            "months_beat_gate3_pass": months_g3_ok,
            "promotion_ready": promotion_ready,
            "live_promotion": False,
            "note": note,
        }

    for lane, vol, vs3 in (
        ("gate5", True, True),
        ("gate6", False, True),
        ("gate7", True, True),
        ("gate8", False, True),
    ):
        out[lane] = _lane_eval(lane, volume_floor=vol, vs_gate3_required=vs3)

    g3 = aggregate.get("gate3", {})
    out["gate3_anchor"] = {
        "aggregate_roi_pct": g3.get("roi_pct"),
        "total_picks": g3.get("picks"),
        "promotion_baseline": True,
        "note": "Gate3 is the paper-trial anchor until ranker restored and slippage >= 300.",
    }
    out["gate_closure"] = {
        "parameter_search_exhausted": True,
        "recommended_paper_lane": "gate3",
        "live_promotion": False,
    }
    return out


def _simulate_allow_reason(
    frame: pd.DataFrame,
    *,
    baseline_col: str,
    reason_col: str,
    raw_col: str,
    reason: str,
    sim_col: str,
) -> pd.DataFrame:
    """Re-admit runners blocked solely by ``reason`` while keeping baseline picks."""
    out = frame.copy()
    base = pd.to_numeric(out[baseline_col], errors="coerce").fillna(0).astype(int).eq(1)
    raw = pd.to_numeric(out[raw_col], errors="coerce").fillna(0).astype(int).eq(1)
    blocked = out[reason_col].astype(str).eq(reason)
    out[sim_col] = (base | (raw & blocked)).astype(int)
    return out


@dataclass
class MarginalReasonRow:
    reason: str
    blocked_count: int
    added_picks: int
    marginal_roi_pct: float | None
    marginal_pnl_units: float
    simulated_roi_pct: float | None
    simulated_picks: int
    simulated_pnl_units: float
    verdict: str

    def to_dict(self) -> dict:
        return {
            "reason": self.reason,
            "blocked_count": self.blocked_count,
            "added_picks": self.added_picks,
            "marginal_roi_pct": self.marginal_roi_pct,
            "marginal_pnl_units": self.marginal_pnl_units,
            "simulated_roi_pct": self.simulated_roi_pct,
            "simulated_picks": self.simulated_picks,
            "simulated_pnl_units": self.simulated_pnl_units,
            "verdict": self.verdict,
        }


def _classify_marginal(marginal_roi: float | None, baseline_roi: float | None) -> str:
    if marginal_roi is None:
        return "no_volume"
    if marginal_roi < 0:
        return "protective"
    if baseline_roi is not None and marginal_roi > baseline_roi + 5.0:
        return "dead_drag"
    if marginal_roi >= 0:
        return "neutral_positive"
    return "review"


def marginal_reason_study(
    frame: pd.DataFrame,
    *,
    baseline_col: str = "flag_gate2",
    reason_col: str = "gate2_reason",
    raw_col: str = "flag_none",
) -> tuple[dict, list[MarginalReasonRow]]:
    """For each block reason, estimate ROI of re-admitting only that cohort."""
    settled = frame[frame["finish_pos"].notna()].copy()
    baseline = _settle(settled, baseline_col)
    base_picks = int(baseline["picks"] or 0)
    base_pnl = float(baseline["pnl_units"] or 0.0)
    base_roi = baseline.get("roi_pct")

    blocked = settled.loc[
        settled[raw_col].eq(1) & settled[baseline_col].eq(0) & settled[reason_col].notna(),
        reason_col,
    ]
    reason_counts = blocked.astype(str).value_counts().to_dict()
    rows: list[MarginalReasonRow] = []

    for reason in sorted(reason_counts.keys()):
        sim_col = f"_sim_allow_{reason}"
        sim_frame = _simulate_allow_reason(
            settled,
            baseline_col=baseline_col,
            reason_col=reason_col,
            raw_col=raw_col,
            reason=reason,
            sim_col=sim_col,
        )
        sim_stats = _settle(sim_frame, sim_col)
        added = int(sim_stats["picks"] or 0) - base_picks
        added_pnl = float(sim_stats["pnl_units"] or 0.0) - base_pnl
        marginal_roi = (added_pnl / added * 100.0) if added > 0 else None
        rows.append(
            MarginalReasonRow(
                reason=reason,
                blocked_count=int(reason_counts[reason]),
                added_picks=added,
                marginal_roi_pct=marginal_roi,
                marginal_pnl_units=added_pnl,
                simulated_roi_pct=sim_stats.get("roi_pct"),
                simulated_picks=int(sim_stats["picks"] or 0),
                simulated_pnl_units=float(sim_stats["pnl_units"] or 0.0),
                verdict=_classify_marginal(marginal_roi, base_roi if isinstance(base_roi, (int, float)) else None),
            )
        )

    rows.sort(key=lambda r: (r.marginal_roi_pct is None, r.marginal_roi_pct or 0.0))
    return baseline, rows


def run_gate_impact(
    *,
    start: str | None = None,
    end: str | None = None,
    database: Path | None = None,
    snapshot_config_hash: str | None = None,
    baseline_col: str = "flag_gate2",
) -> dict:
    cfg = load_config()
    db = database or db_path(cfg)
    paper_cfg = cfg.get("paper", {})
    max_start, max_end = _historical_bounds(db)
    start_s = start or max_start
    end_s = end or max_end
    if not start_s or not end_s:
        return {"error": "no historical settled data", "start": start_s, "end": end_s}

    snap_hash = resolve_snapshot_config_hash(db, paper_cfg, explicit=snapshot_config_hash)
    snap = load_snapshots(db, start_s, end_s, config_hash=snap_hash)
    if snap.empty:
        return {
            "error": "no snapshots for window",
            "start": start_s,
            "end": end_s,
            "snapshot_config_hash": snap_hash,
        }

    gated = _apply_gate_flags(snap, paper_cfg)
    gated = gated[gated["finish_pos"].notna()].copy()
    gated = apply_experimental_lanes(gated, paper_cfg, full_cfg=cfg)

    reason_col = {
        "flag_gate2": "gate2_reason",
        "flag_gate1": "gate1_reason",
        "flag_production": "production_reason",
    }.get(baseline_col, "gate2_reason")

    baseline_stats, marginal_rows = marginal_reason_study(
        gated,
        baseline_col=baseline_col,
        reason_col=reason_col,
        raw_col="flag_none",
    )

    lanes = {
        "none": _settle(gated, "flag_none"),
        "gate1": _settle(gated, "flag_gate1"),
        **_experimental_lane_stats(gated),
    }
    comparisons = {
        "gate3_vs_gate2": _delta(lanes["gate3"], lanes["gate2"]),
        "gate4_vs_gate2": _delta(lanes["gate4"], lanes["gate2"]),
        "gate5_vs_gate3": _delta(lanes["gate5"], lanes["gate3"]),
        "gate6_vs_gate3": _delta(lanes["gate6"], lanes["gate3"]),
        "gate7_vs_gate3": _delta(lanes["gate7"], lanes["gate3"]),
        "gate8_vs_gate3": _delta(lanes["gate8"], lanes["gate3"]),
        "gate2_vs_none": _delta(lanes["gate2"], lanes["none"]),
    }

    return {
        "start": start_s,
        "end": end_s,
        "snapshot_config_hash": snap_hash,
        "card_days": int(gated["card_date"].nunique()),
        "runners": len(gated),
        "baseline_lane": baseline_col,
        "baseline": baseline_stats,
        "marginal_reasons": [r.to_dict() for r in marginal_rows],
        "lanes": lanes,
        "comparisons": comparisons,
        "lane_configs": {
            "gate3": gate3_config(paper_cfg, cfg).get("gate2"),
            "gate5": gate5_config(paper_cfg, cfg).get("gate2"),
            "gate7": gate7_config(paper_cfg, cfg).get("gate2"),
            "gate8": _lane_spec(cfg, "gate8_regime_blend"),
        },
        "message": (
            f"Gate impact {start_s} → {end_s}: gate2={lanes['gate2'].get('roi_pct')}, "
            f"gate3={lanes['gate3'].get('roi_pct')}, gate7={lanes['gate7'].get('roi_pct')}, "
            f"gate8={lanes['gate8'].get('roi_pct')}."
        ),
    }


def _aggregate_stats(stats_rows: list[dict]) -> dict[str, float | int | None]:
    picks = sum(int(r.get("picks") or 0) for r in stats_rows)
    settled = sum(int(r.get("settled") or 0) for r in stats_rows)
    pnl = sum(float(r.get("pnl_units") or 0.0) for r in stats_rows)
    if not settled:
        return {"picks": 0, "settled": 0, "hit_rate": None, "roi_pct": None, "pnl_units": 0.0}
    hit_num = sum(
        float(r["hit_rate"]) * int(r["settled"])
        for r in stats_rows
        if r.get("hit_rate") is not None and int(r.get("settled") or 0) > 0
    )
    return {
        "picks": picks,
        "settled": settled,
        "hit_rate": hit_num / settled,
        "roi_pct": (pnl / settled) * 100,
        "pnl_units": pnl,
    }


def _lane_stats_for_window(
    *,
    db: Path,
    start: str,
    end: str,
    paper_cfg: dict,
    snap_hash: str,
    full_cfg: dict,
) -> tuple[pd.DataFrame, dict[str, dict]]:
    snap = load_snapshots(db, start, end, config_hash=snap_hash)
    if snap.empty:
        return pd.DataFrame(), {}
    gated = _apply_gate_flags(snap, paper_cfg)
    gated = gated[gated["finish_pos"].notna()].copy()
    gated = apply_experimental_lanes(gated, paper_cfg, full_cfg=full_cfg)
    return gated, _experimental_lane_stats(gated)


def _count_roi_wins(period_rows: list[dict], lane: str, vs: str) -> int:
    wins = 0
    for row in period_rows:
        if int(row.get("gate2", {}).get("picks") or 0) <= 0:
            continue
        a, b = row.get(lane, {}), row.get(vs, {})
        ar, br = a.get("roi_pct"), b.get("roi_pct")
        if ar is not None and br is not None and ar > br:
            wins += 1
    return wins


def run_gate_lane_walkforward(
    *,
    start: str | None = None,
    end: str | None = None,
    database: Path | None = None,
    snapshot_config_hash: str | None = None,
    progress_path: Path | None = None,
) -> dict:
    """Month-by-month Gate2 vs Gate3–8 on snapshot replay with promotion evaluation."""
    cfg = load_config()
    db = database or db_path(cfg)
    paper_cfg = cfg.get("paper", {})
    max_start, max_end = _historical_bounds(db)
    start_s = start or max_start
    end_s = end or max_end
    if not start_s or not end_s:
        return {"error": "no historical settled data", "start": start_s, "end": end_s}

    snap_hash = resolve_snapshot_config_hash(db, paper_cfg, explicit=snapshot_config_hash)
    month_windows = _month_periods(date.fromisoformat(start_s), date.fromisoformat(end_s))
    period_rows: list[dict] = []
    focus_lanes = WALKFORWARD_FOCUS_LANES
    lane_rows: dict[str, list[dict]] = {lane: [] for lane in focus_lanes}
    months_with_data = 0

    for label, p_start, p_end in month_windows:
        gated, lanes = _lane_stats_for_window(
            db=db,
            start=p_start,
            end=p_end,
            paper_cfg=paper_cfg,
            snap_hash=snap_hash,
            full_cfg=cfg,
        )
        row: dict = {
            "period": label,
            "start": p_start,
            "end": p_end,
            "card_days": int(gated["card_date"].nunique()) if not gated.empty else 0,
        }
        if lanes:
            for lane in focus_lanes:
                row[lane] = lanes.get(lane, {})
            row["delta_gate3_vs_gate2"] = _delta(lanes["gate3"], lanes["gate2"])
            row["delta_gate7_vs_gate3"] = _delta(lanes["gate7"], lanes["gate3"])
            row["delta_gate8_vs_gate3"] = _delta(lanes["gate8"], lanes["gate3"])
        period_rows.append(row)
        if progress_path is not None:
            progress_path.parent.mkdir(parents=True, exist_ok=True)
            progress_path.write_text(
                json.dumps(
                    {
                        "start": start_s,
                        "end": end_s,
                        "snapshot_config_hash": snap_hash,
                        "completed_periods": period_rows,
                        "last_period": label,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
        if not lanes or int(lanes["gate2"].get("picks") or 0) == 0:
            continue
        months_with_data += 1
        for lane in focus_lanes:
            lane_rows[lane].append(lanes[lane])

    aggregate = {lane: _aggregate_stats(lane_rows[lane]) for lane in focus_lanes}
    aggregate["delta_gate3_vs_gate2"] = _delta(aggregate["gate3"], aggregate["gate2"])
    aggregate["delta_gate7_vs_gate3"] = _delta(aggregate["gate7"], aggregate["gate3"])
    aggregate["delta_gate8_vs_gate3"] = _delta(aggregate["gate8"], aggregate["gate3"])

    promotion = evaluate_lane_promotion(
        aggregate=aggregate,
        period_rows=period_rows,
        months_with_data=months_with_data,
        full_cfg=cfg,
    )

    return {
        "start": start_s,
        "end": end_s,
        "snapshot_config_hash": snap_hash,
        "months_total": len(month_windows),
        "months_with_data": months_with_data,
        "gate3_roi_wins_vs_gate2": _count_roi_wins(period_rows, "gate3", "gate2"),
        "gate7_roi_wins_vs_gate3": _count_roi_wins(period_rows, "gate7", "gate3"),
        "gate8_roi_wins_vs_gate3": _count_roi_wins(period_rows, "gate8", "gate3"),
        "aggregate": aggregate,
        "periods": period_rows,
        "promotion_evaluation": promotion,
        "promotion_criteria": _promotion_criteria(cfg),
        "lane_configs": {
            "gate3": gate3_config(paper_cfg, cfg).get("gate2"),
            "gate7": gate7_config(paper_cfg, cfg).get("gate2"),
            "gate8": _lane_spec(cfg, "gate8_regime_blend"),
        },
        "message": (
            f"Gate closure walk-forward {start_s} → {end_s}: "
            f"gate2={aggregate['gate2'].get('roi_pct')}, gate3={aggregate['gate3'].get('roi_pct')}, "
            f"gate7={aggregate['gate7'].get('roi_pct')}, gate8={aggregate['gate8'].get('roi_pct')}. "
            f"Paper anchor: gate3."
        ),
    }
