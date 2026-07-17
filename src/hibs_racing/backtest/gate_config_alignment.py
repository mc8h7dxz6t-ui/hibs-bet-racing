"""Forensic gate alignment — industry-standard anchors, aligned overlays, blends, output matrix."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from hibs_racing.backtest.db_resolve import resolve_backtest_database
from hibs_racing.backtest.gate_benchmark import (
    _apply_gate_flags,
    _delta,
    _historical_bounds,
    _settle,
)
from hibs_racing.backtest.gate_impact import (
    _apply_lane_from_none,
    _promotion_criteria,
    _rank_col,
    apply_experimental_lanes,
    gate3_config,
    gate7_config,
)
from hibs_racing.backtest.snapshot_store import load_snapshots, resolve_snapshot_config_hash
from hibs_racing.cards.actionability import _gate2_confidence
from hibs_racing.config import load_config

# --- Three evidence-backed industry standards (forensic anchors) ---

INDUSTRY_STANDARD_ANCHORS: dict[str, dict[str, Any]] = {
    "std_institutional_gate3": {
        "standard": "Institutional paper anchor",
        "evidence": (
            "gate_closure.recommended_paper_lane=gate3; 7/7 months beat gate2; "
            "+74.7% walkforward ROI (exports/gate_lane_walkforward.json)"
        ),
        "source": "PORTFOLIO Program 4 / ingest/config.yaml gate_closure",
        "lane_kind": "gate3",
    },
    "std_regime_blend_gate8": {
        "standard": "Regime-blend successor",
        "evidence": (
            "+147.6% ROI; only experimental lane with positive PnL units vs gate3 (+41.1); "
            "7/7 months beat gate3"
        ),
        "source": "PORTFOLIO Program 8 / experimental_replay_lanes.gate8_regime_blend",
        "lane_kind": "gate8",
    },
    "std_production_gate2": {
        "standard": "Production caps-on gate2",
        "evidence": (
            "Live deployment lane; gate2 caps ON +51.5% vs caps OFF -1.5% (gate2_sensitivity_60d); "
            "production_benchmark_90d +48.5%"
        ),
        "source": "ingest/config.yaml paper + gate2_sensitivity / production_benchmark",
        "lane_kind": "production",
    },
}

# --- Three overlays aligned 1:1 to each standard (not blind tweaks) ---

ALIGNED_OVERLAY_SPECS: dict[str, dict[str, Any]] = {
    "aligned_institutional_gate3": {
        "aligns_to": "std_institutional_gate3",
        "description": "Exact gate3 institutional paper anchor — OR50 RTF10 conf0.60 cap2/4",
        "lane_kind": "gate3",
    },
    "aligned_regime_gate8": {
        "aligns_to": "std_regime_blend_gate8",
        "description": "Gate8 regime blend — gate3 core + confidence-tiered caps (trigger 0.70)",
        "lane_kind": "gate8",
    },
    "aligned_sniper_gate7": {
        "aligns_to": "std_production_gate2",
        "description": (
            "Premium sniper overlay on production stack — OR65 RTF20 conf0.65 cap1/1 "
            "(selective tier above live gate2)"
        ),
        "lane_kind": "gate7",
    },
}

# --- Two forensic blends of top replay performers ---

BLEND_SPECS: dict[str, dict[str, Any]] = {
    "blend_gate8_gate7": {
        "description": "Gate7 sniper selectivity + Gate8 dynamic caps (best ROI% + best PnL blend)",
        "base_lane": "gate7",
        "regime_blend": {
            "trigger_confidence": 0.70,
            "default_max_value_per_race": 2,
            "default_max_value_per_meeting": 3,
            "escalated_max_value_per_race": 1,
            "escalated_max_value_per_meeting": 1,
        },
    },
    "blend_gate3_gate7": {
        "description": "Gate3 institutional core + Gate7 OR/RTF/caps (anchor strictness + sniper density)",
        "base_lane": "gate3_gate7_hybrid",
        "regime_blend": None,
        "hybrid": {
            "from_gate3": ("min_confidence", "min_stressed_place_ev"),
            "from_gate7": ("min_official_rating", "min_trainer_rtf", "max_value_per_race", "max_value_per_meeting"),
        },
    },
}


@dataclass(frozen=True)
class LaneRunner:
    lane_id: str
    category: str  # canonical | aligned | blend
    description: str
    apply: Callable[[pd.DataFrame, dict, dict], pd.DataFrame]


def _gate7_paper(paper_cfg: dict, full_cfg: dict) -> dict:
    return gate7_config(paper_cfg, full_cfg)


def _gate3_paper(paper_cfg: dict, full_cfg: dict) -> dict:
    return gate3_config(paper_cfg, full_cfg)


def _hybrid_gate3_gate7_paper(paper_cfg: dict, full_cfg: dict) -> dict:
    g3 = gate3_config(deepcopy(paper_cfg), full_cfg)
    g7 = gate7_config(deepcopy(paper_cfg), full_cfg)
    g2 = g3.setdefault("gate2", {})
    g7g2 = g7.get("gate2") or {}
    if isinstance(g2, dict) and isinstance(g7g2, dict):
        g3["min_official_rating"] = g7.get("min_official_rating", g3.get("min_official_rating"))
        g3["min_trainer_rtf"] = g7.get("min_trainer_rtf", g3.get("min_trainer_rtf"))
        g2["max_value_per_race"] = g7g2.get("max_value_per_race", 1)
        g2["max_value_per_meeting"] = g7g2.get("max_value_per_meeting", 1)
    return g3


def apply_regime_blend_lane(
    frame: pd.DataFrame,
    base_paper_cfg: dict,
    *,
    blend_spec: dict,
    flag_col: str,
    reason_col: str,
) -> pd.DataFrame:
    """Gate8-style tiered caps on an arbitrary base paper config."""
    trigger = float(blend_spec.get("trigger_confidence", 0.70))
    default_race = int(blend_spec.get("default_max_value_per_race", 2))
    default_meeting = int(blend_spec.get("default_max_value_per_meeting", 4))
    escalated_race = int(blend_spec.get("escalated_max_value_per_race", 1))
    escalated_meeting = int(blend_spec.get("escalated_max_value_per_meeting", 2))

    cfg = deepcopy(base_paper_cfg)
    g2 = cfg.setdefault("gate2", {})
    if isinstance(g2, dict):
        g2["max_value_per_race"] = None
        g2["max_value_per_meeting"] = None

    precap_col = f"_{flag_col}_precap"
    out = _apply_lane_from_none(frame, cfg, precap_col, reason_col)
    rank = _rank_col(out)
    flags = pd.Series(0, index=out.index, dtype=int)
    race_counts: dict[str, int] = {}
    meeting_counts: dict[tuple[str, str], int] = {}

    candidates = out[out[precap_col].eq(1)].copy()
    if not candidates.empty:
        candidates = candidates.sort_values([rank], ascending=False, na_position="last")
        for idx, row in candidates.iterrows():
            conf = _gate2_confidence(row, cfg)
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

    out[flag_col] = flags.astype(int)
    out.loc[out[flag_col].eq(0) & out[precap_col].eq(1), reason_col] = "blend_tier_cap"
    out.loc[out[flag_col].eq(1), reason_col] = None
    return out.drop(columns=[precap_col], errors="ignore")


def _apply_blend_gate8_gate7(frame: pd.DataFrame, paper_cfg: dict, full_cfg: dict) -> pd.DataFrame:
    base = _gate7_paper(paper_cfg, full_cfg)
    spec = BLEND_SPECS["blend_gate8_gate7"]["regime_blend"]
    return apply_regime_blend_lane(
        frame,
        base,
        blend_spec=spec,
        flag_col="flag_blend_gate8_gate7",
        reason_col="blend_gate8_gate7_reason",
    )


def _apply_blend_gate3_gate7(frame: pd.DataFrame, paper_cfg: dict, full_cfg: dict) -> pd.DataFrame:
    cfg = _hybrid_gate3_gate7_paper(paper_cfg, full_cfg)
    return _apply_lane_from_none(frame, cfg, "flag_blend_gate3_gate7", "blend_gate3_gate7_reason")


def _apply_aligned_gate7(frame: pd.DataFrame, paper_cfg: dict, full_cfg: dict) -> pd.DataFrame:
    return _apply_lane_from_none(
        frame,
        _gate7_paper(paper_cfg, full_cfg),
        "flag_aligned_sniper_gate7",
        "aligned_sniper_gate7_reason",
    )


def _apply_aligned_gate3(frame: pd.DataFrame, paper_cfg: dict, full_cfg: dict) -> pd.DataFrame:
    return _apply_lane_from_none(
        frame,
        _gate3_paper(paper_cfg, full_cfg),
        "flag_aligned_institutional_gate3",
        "aligned_institutional_gate3_reason",
    )


def _apply_aligned_gate8(frame: pd.DataFrame, paper_cfg: dict, full_cfg: dict) -> pd.DataFrame:
    out = apply_experimental_lanes(frame, paper_cfg, full_cfg)
    out = out.rename(columns={"flag_gate8": "flag_aligned_regime_gate8"})
    if "gate8_reason" in out.columns:
        out = out.rename(columns={"gate8_reason": "aligned_regime_gate8_reason"})
    return out


def _lane_runners() -> list[LaneRunner]:
    return [
        LaneRunner("gate2", "canonical", "Production gate2 (caps on)", lambda f, p, c: f),
        LaneRunner("gate3", "canonical", "Institutional paper anchor", lambda f, p, c: f),
        LaneRunner("gate5", "canonical", "Gate5 sniper expansion", lambda f, p, c: f),
        LaneRunner("gate6", "canonical", "Gate6 market-bounded", lambda f, p, c: f),
        LaneRunner("gate7", "canonical", "Gate7 true sniper", lambda f, p, c: f),
        LaneRunner("gate8", "canonical", "Gate8 regime blend", lambda f, p, c: f),
        LaneRunner("production", "canonical", "Live production lane", lambda f, p, c: f),
        LaneRunner(
            "aligned_institutional_gate3",
            "aligned",
            ALIGNED_OVERLAY_SPECS["aligned_institutional_gate3"]["description"],
            _apply_aligned_gate3,
        ),
        LaneRunner(
            "aligned_regime_gate8",
            "aligned",
            ALIGNED_OVERLAY_SPECS["aligned_regime_gate8"]["description"],
            _apply_aligned_gate8,
        ),
        LaneRunner(
            "aligned_sniper_gate7",
            "aligned",
            ALIGNED_OVERLAY_SPECS["aligned_sniper_gate7"]["description"],
            _apply_aligned_gate7,
        ),
        LaneRunner(
            "blend_gate8_gate7",
            "blend",
            BLEND_SPECS["blend_gate8_gate7"]["description"],
            _apply_blend_gate8_gate7,
        ),
        LaneRunner(
            "blend_gate3_gate7",
            "blend",
            BLEND_SPECS["blend_gate3_gate7"]["description"],
            _apply_blend_gate3_gate7,
        ),
    ]


def _prepare_gated_frame(snap: pd.DataFrame, paper_cfg: dict) -> pd.DataFrame:
    gated = _apply_gate_flags(snap, paper_cfg)
    gated = gated[gated["finish_pos"].notna()].copy()
    gated["flag_none"] = pd.to_numeric(gated["flag_raw"], errors="coerce").fillna(0).astype(int)
    return gated


def _stats_for_lane(gated: pd.DataFrame, runner: LaneRunner, paper_cfg: dict, full_cfg: dict) -> dict:
    if runner.lane_id in ("gate2", "gate3", "gate5", "gate6", "gate7", "gate8", "production"):
        if runner.lane_id == "gate8":
            exp = apply_experimental_lanes(gated, paper_cfg, full_cfg)
            return _settle(exp, "flag_gate8")
        col = f"flag_{runner.lane_id}"
        if runner.lane_id == "production":
            col = "flag_production"
        exp = apply_experimental_lanes(gated, paper_cfg, full_cfg) if runner.lane_id in (
            "gate3",
            "gate5",
            "gate6",
            "gate7",
        ) else gated
        if runner.lane_id in ("gate3", "gate5", "gate6", "gate7"):
            return _settle(exp, f"flag_{runner.lane_id}")
        return _settle(gated if runner.lane_id in ("gate2", "production") else exp, col)

    worked = runner.apply(gated, paper_cfg, full_cfg)
    flag_map = {
        "aligned_institutional_gate3": "flag_aligned_institutional_gate3",
        "aligned_regime_gate8": "flag_aligned_regime_gate8",
        "aligned_sniper_gate7": "flag_aligned_sniper_gate7",
        "blend_gate8_gate7": "flag_blend_gate8_gate7",
        "blend_gate3_gate7": "flag_blend_gate3_gate7",
    }
    return _settle(worked, flag_map[runner.lane_id])


def _evaluate_row(
    lane_id: str,
    stats: dict,
    *,
    gate3_stats: dict,
    months_with_data: int,
    crit: dict,
) -> dict:
    picks = int(stats.get("picks") or 0)
    roi = stats.get("roi_pct")
    g3_roi = gate3_stats.get("roi_pct")
    avg_monthly = (picks / months_with_data) if months_with_data else 0.0
    volume_ok = avg_monthly >= crit["min_picks_per_month_gate5"]
    roi_ok = isinstance(roi, (int, float)) and float(roi) >= crit["min_aggregate_roi_pct"]
    beats_g3 = (
        isinstance(roi, (int, float))
        and isinstance(g3_roi, (int, float))
        and float(roi) > float(g3_roi)
    )
    return {
        "picks": picks,
        "settled": stats.get("settled"),
        "hit_rate": stats.get("hit_rate"),
        "roi_pct": roi,
        "pnl_units": stats.get("pnl_units"),
        "avg_picks_per_dense_month": round(avg_monthly, 1),
        "volume_floor_pass": volume_ok,
        "aggregate_roi_pass": roi_ok,
        "beats_gate3_roi": beats_g3,
        "delta_vs_gate3_pp": _delta(stats, gate3_stats).get("roi_change_pp"),
    }


def format_gate_matrix_table(rows: list[dict]) -> str:
    """Markdown table of all gate lane outputs."""
    header = (
        "| Lane | Category | Picks | Hit% | ROI% | PnL units | vs G3 (pp) | Vol OK | Beats G3 |"
    )
    sep = "|---|---|--:|--:|--:|--:|--:|:--:|:--:|"
    lines = [
        "# Gate alignment matrix",
        "",
        header,
        sep,
    ]
    for row in rows:
        hit = row.get("hit_rate")
        hit_s = f"{100 * hit:.1f}" if isinstance(hit, (int, float)) else "—"
        roi = row.get("roi_pct")
        roi_s = f"{roi:.1f}" if isinstance(roi, (int, float)) else "—"
        pnl = row.get("pnl_units")
        pnl_s = f"{pnl:.1f}" if isinstance(pnl, (int, float)) else "—"
        dpp = row.get("delta_vs_gate3_pp")
        dpp_s = f"{dpp:+.1f}" if isinstance(dpp, (int, float)) else "—"
        vol = "✓" if row.get("volume_floor_pass") else "✗"
        beat = "✓" if row.get("beats_gate3_roi") else "✗"
        lines.append(
            f"| {row['lane_id']} | {row['category']} | {row.get('picks', 0)} | {hit_s} | "
            f"{roi_s} | {pnl_s} | {dpp_s} | {vol} | {beat} |"
        )
    lines.append("")
    return "\n".join(lines)


def run_gate_alignment_matrix(
    *,
    start: str | None = None,
    end: str | None = None,
    database: Path | None = None,
    snapshot_config_hash: str | None = None,
) -> dict:
    """Run all canonical lanes + 3 aligned overlays + 2 blends; return ranked matrix."""
    cfg = load_config()
    try:
        db = database or resolve_backtest_database(cfg)[0]
    except FileNotFoundError as exc:
        return {"error": str(exc), "start": start, "end": end}
    paper_cfg = cfg.get("paper", {})
    if start and end:
        start_s, end_s = start, end
    else:
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

    gated = _prepare_gated_frame(snap, paper_cfg)
    crit = _promotion_criteria(cfg)
    runners = _lane_runners()
    lane_stats: dict[str, dict] = {}
    for runner in runners:
        lane_stats[runner.lane_id] = _stats_for_lane(gated, runner, paper_cfg, cfg)

    gate3_stats = lane_stats.get("gate3", {})
    months_with_data = max(
        1,
        len({str(d)[:7] for d in snap["card_date"].dropna().astype(str).unique()}),
    )

    matrix_rows: list[dict] = []
    for runner in runners:
        stats = lane_stats[runner.lane_id]
        eval_row = _evaluate_row(
            runner.lane_id,
            stats,
            gate3_stats=gate3_stats,
            months_with_data=months_with_data,
            crit=crit,
        )
        matrix_rows.append(
            {
                "lane_id": runner.lane_id,
                "category": runner.category,
                "description": runner.description,
                **eval_row,
            }
        )

    matrix_rows.sort(
        key=lambda r: (
            1 if r.get("beats_gate3_roi") else 0,
            float(r["roi_pct"]) if isinstance(r.get("roi_pct"), (int, float)) else -1e9,
            int(r.get("picks") or 0),
        ),
        reverse=True,
    )

    best_blend = next((r for r in matrix_rows if r["category"] == "blend"), None)
    best_aligned = next((r for r in matrix_rows if r["category"] == "aligned"), None)

    return {
        "start": start_s,
        "end": end_s,
        "snapshot_config_hash": snap_hash,
        "card_days": int(snap["card_date"].nunique()),
        "runners": len(snap),
        "industry_standards": INDUSTRY_STANDARD_ANCHORS,
        "aligned_overlays": ALIGNED_OVERLAY_SPECS,
        "blend_specs": BLEND_SPECS,
        "promotion_criteria": crit,
        "matrix": matrix_rows,
        "matrix_table_markdown": format_gate_matrix_table(matrix_rows),
        "best_blend": best_blend,
        "best_aligned_overlay": best_aligned,
        "message": (
            f"Gate alignment matrix {start_s} → {end_s}: "
            f"top={matrix_rows[0]['lane_id']} roi={matrix_rows[0].get('roi_pct')}% "
            f"best_blend={best_blend['lane_id'] if best_blend else None}."
        ),
    }


def merge_walkforward_reference(matrix_report: dict, walkforward_path: Path) -> dict:
    """Attach prior walkforward aggregates for forensic cross-check."""
    if not walkforward_path.is_file():
        return matrix_report
    wf = json.loads(walkforward_path.read_text(encoding="utf-8"))
    ref = wf.get("aggregate") or {}
    matrix_report["walkforward_reference"] = {
        "source": str(walkforward_path),
        "window": f"{wf.get('start')} → {wf.get('end')}",
        "lanes": {k: v for k, v in ref.items() if isinstance(v, dict) and "roi_pct" in v},
    }
    return matrix_report
