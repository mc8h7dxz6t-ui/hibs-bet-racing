"""Walk-forward sweep of tweaked sniper gate overlays (Gate3 core + OR/RTF/caps/EV floors)."""

from __future__ import annotations

import json
from copy import deepcopy
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
from hibs_racing.backtest.gate_impact import (
    _aggregate_stats,
    _apply_lane_from_none,
    _merge_lane_spec,
    _promotion_criteria,
    gate3_config,
    gate5_config,
    gate7_config,
)
from hibs_racing.backtest.snapshot_store import load_snapshots, resolve_snapshot_config_hash
from hibs_racing.config import db_path, load_config

_PAPER_LEVEL_KEYS: frozenset[str] = frozenset(
    {
        "min_place_ev",
        "min_combo_bayes_place",
        "harville_longshot_win_prob_threshold",
        "harville_longshot_discount",
        "exempt_unrated_races",
        "require_official_rating_for_value",
    }
)

# Eight replay-only overlays — tweak OR/RTF/confidence/stressed EV/caps and EV floors.
SNIPER_OVERLAY_VARIANTS: dict[str, dict[str, Any]] = {
    "gate5_baseline": {
        "description": "Current gate5_sniper YAML — OR60 RTF15 conf0.65 stressed0.05 cap1/2",
        "min_official_rating": 60,
        "min_trainer_rtf": 15,
        "gate2": {
            "min_confidence": 0.65,
            "min_stressed_place_ev": 0.05,
            "max_value_per_race": 1,
            "max_value_per_meeting": 2,
        },
    },
    "gate7_baseline": {
        "description": "Current gate7_true_sniper — OR65 RTF20 conf0.65 stressed0.05 cap1/1",
        "min_official_rating": 65,
        "min_trainer_rtf": 20,
        "min_confidence": 0.65,
        "min_stressed_place_ev": 0.05,
        "max_value_per_race": 1,
        "max_value_per_meeting": 1,
    },
    "sniper_loose": {
        "description": "More volume — OR55 RTF10 conf0.60 stressed0.03 cap2/3",
        "min_official_rating": 55,
        "min_trainer_rtf": 10,
        "gate2": {
            "min_confidence": 0.60,
            "min_stressed_place_ev": 0.03,
            "max_value_per_race": 2,
            "max_value_per_meeting": 3,
        },
    },
    "sniper_mid": {
        "description": "Between gate5 and gate7 — OR62 RTF17 conf0.67 stressed0.05 cap1/2",
        "min_official_rating": 62,
        "min_trainer_rtf": 17,
        "gate2": {
            "min_confidence": 0.67,
            "min_stressed_place_ev": 0.05,
            "max_value_per_race": 1,
            "max_value_per_meeting": 2,
        },
    },
    "sniper_ultra": {
        "description": "Tighter than gate7 — OR68 RTF22 conf0.70 stressed0.07 cap1/1",
        "min_official_rating": 68,
        "min_trainer_rtf": 22,
        "gate2": {
            "min_confidence": 0.70,
            "min_stressed_place_ev": 0.07,
            "max_value_per_race": 1,
            "max_value_per_meeting": 1,
        },
    },
    "sniper_ev_floor": {
        "description": "Gate5 core + higher place EV floor (0.08) and combo 0.25",
        "min_official_rating": 60,
        "min_trainer_rtf": 15,
        "min_place_ev": 0.08,
        "min_combo_bayes_place": 0.25,
        "gate2": {
            "min_confidence": 0.65,
            "min_stressed_place_ev": 0.05,
            "max_value_per_race": 1,
            "max_value_per_meeting": 2,
        },
    },
    "sniper_sale_style": {
        "description": "Sale-gate style EV floors — min_place_ev0.10 combo0.28 on gate5 core",
        "min_official_rating": 60,
        "min_trainer_rtf": 15,
        "min_place_ev": 0.10,
        "min_combo_bayes_place": 0.28,
        "gate2": {
            "min_confidence": 0.65,
            "min_stressed_place_ev": 0.05,
            "max_value_per_race": 1,
            "max_value_per_meeting": 2,
            "min_place_ev_medium": 0.10,
            "min_combo_medium": 0.28,
        },
    },
    "sniper_market_band": {
        "description": "Gate5 + SP band 2.5–9.0 — avoid short favs and long outsiders",
        "min_official_rating": 60,
        "min_trainer_rtf": 15,
        "gate2": {
            "min_confidence": 0.65,
            "min_stressed_place_ev": 0.05,
            "max_value_per_race": 1,
            "max_value_per_meeting": 2,
            "min_win_decimal": 2.5,
            "max_win_decimal": 9.0,
        },
    },
}


def overlay_variant_ids() -> tuple[str, ...]:
    return tuple(SNIPER_OVERLAY_VARIANTS.keys())


def build_overlay_paper_cfg(paper_cfg: dict, overlay_spec: dict) -> dict:
    """Gate3 core merged with one overlay variant (paper-level + gate2 keys)."""
    base = gate3_config(deepcopy(paper_cfg), {"paper": paper_cfg, "experimental_replay_lanes": {}})
    for key in _PAPER_LEVEL_KEYS:
        if key in overlay_spec:
            base[key] = overlay_spec[key]
    lane_spec = {k: v for k, v in overlay_spec.items() if k not in _PAPER_LEVEL_KEYS and k != "description"}
    return _merge_lane_spec(base, lane_spec)


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


def evaluate_overlay_promotion(
    *,
    overlay_id: str,
    aggregate: dict[str, dict],
    period_rows: list[dict],
    months_with_data: int,
    full_cfg: dict,
) -> dict:
    """Promotion-style checks for a custom overlay vs gate3 anchor."""
    crit = _promotion_criteria(full_cfg)
    overlay = aggregate.get("overlay", {})
    gate3 = aggregate.get("gate3", {})
    picks = int(overlay.get("picks") or 0)
    roi = overlay.get("roi_pct")
    g3_roi = gate3.get("roi_pct")
    avg_monthly = (picks / months_with_data) if months_with_data else 0.0
    beat_g2 = _monthly_roi_wins(period_rows, "overlay", vs="gate2")
    beat_g3 = _monthly_roi_wins(period_rows, "overlay", vs="gate3")
    volume_ok = avg_monthly >= crit["min_picks_per_month_gate5"]
    roi_ok = isinstance(roi, (int, float)) and float(roi) >= crit["min_aggregate_roi_pct"]
    beats_g3_agg = (
        isinstance(roi, (int, float))
        and isinstance(g3_roi, (int, float))
        and float(roi) > float(g3_roi)
    )
    months_g2_ok = beat_g2 >= crit["min_months_beat_gate2"]
    months_g3_ok = beat_g3 >= crit["min_months_beat_gate3"]
    sniper_too_thin = avg_monthly < crit["min_picks_per_month_gate5"]
    promotion_ready = bool(
        volume_ok and roi_ok and months_g2_ok and months_g3_ok and beats_g3_agg
    )
    note = "Replay-only until scoring hash stable + slippage sample >= 300."
    if sniper_too_thin:
        note = (
            "Volume below sniper floor — cannot build reliable edge on thin pool; "
            "focus on ranker fix, not tighter gates."
        )
    return {
        "overlay_id": overlay_id,
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


def _lane_stats_for_overlay(
    frame: pd.DataFrame,
    paper_cfg: dict,
    overlay_spec: dict,
    full_cfg: dict,
) -> dict[str, dict]:
    base = _apply_gate_flags(frame, paper_cfg)
    base = base[base["finish_pos"].notna()].copy()

    def _one_lane(lane_cfg: dict) -> dict:
        gated = _apply_lane_from_none(base, lane_cfg, "flag_lane", "lane_reason")
        return _settle(gated, "flag_lane")

    return {
        "overlay": _one_lane(build_overlay_paper_cfg(paper_cfg, overlay_spec)),
        "gate3": _one_lane(gate3_config(paper_cfg, full_cfg)),
        "gate2": _settle(base, "flag_gate2"),
        "gate5": _one_lane(gate5_config(paper_cfg, full_cfg)),
        "gate7": _one_lane(gate7_config(paper_cfg, full_cfg)),
    }


def _rank_key(row: dict) -> tuple:
    roi = row.get("aggregate_roi_pct")
    picks = int(row.get("total_picks") or 0)
    return (
        1 if row.get("promotion_ready") else 0,
        float(roi) if isinstance(roi, (int, float)) else -1e9,
        picks,
    )


def run_sniper_overlay_sweep(
    *,
    start: str | None = None,
    end: str | None = None,
    database: Path | None = None,
    snapshot_config_hash: str | None = None,
    variants: dict[str, dict[str, Any]] | None = None,
    progress_path: Path | None = None,
) -> dict:
    """Run walk-forward backtest for each sniper overlay variant; rank by promotion + ROI."""
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
    overlay_defs = variants or SNIPER_OVERLAY_VARIANTS
    crit = _promotion_criteria(cfg)

    results: dict[str, dict] = {}
    for overlay_id, spec in overlay_defs.items():
        period_rows: list[dict] = []
        lane_rows: dict[str, list[dict]] = {"overlay": [], "gate3": [], "gate2": [], "gate5": [], "gate7": []}
        months_with_data = 0

        for label, p_start, p_end in month_windows:
            snap = load_snapshots(db, p_start, p_end, config_hash=snap_hash)
            row: dict[str, Any] = {
                "period": label,
                "start": p_start,
                "end": p_end,
                "card_days": int(snap["card_date"].nunique()) if not snap.empty else 0,
            }
            if not snap.empty:
                lanes = _lane_stats_for_overlay(snap, paper_cfg, spec, cfg)
                for lane in lane_rows:
                    row[lane] = lanes.get(lane, {})
                row["delta_overlay_vs_gate3"] = _delta(lanes["overlay"], lanes["gate3"])
                row["delta_overlay_vs_gate7"] = _delta(lanes["overlay"], lanes["gate7"])
            period_rows.append(row)
            if snap.empty or int(row.get("gate2", {}).get("picks") or 0) == 0:
                continue
            months_with_data += 1
            for lane in lane_rows:
                lane_rows[lane].append(row[lane])

        aggregate = {lane: _aggregate_stats(lane_rows[lane]) for lane in lane_rows}
        aggregate["delta_overlay_vs_gate3"] = _delta(aggregate["overlay"], aggregate["gate3"])
        aggregate["delta_overlay_vs_gate7"] = _delta(aggregate["overlay"], aggregate["gate7"])
        promotion = evaluate_overlay_promotion(
            overlay_id=overlay_id,
            aggregate=aggregate,
            period_rows=period_rows,
            months_with_data=months_with_data,
            full_cfg=cfg,
        )
        results[overlay_id] = {
            "description": spec.get("description", ""),
            "overlay_spec": {k: v for k, v in spec.items() if k != "description"},
            "overlay_paper_cfg": build_overlay_paper_cfg(paper_cfg, spec),
            "months_with_data": months_with_data,
            "aggregate": aggregate,
            "periods": period_rows,
            "promotion": promotion,
        }

        if progress_path is not None:
            progress_path.parent.mkdir(parents=True, exist_ok=True)
            progress_path.write_text(
                json.dumps(
                    {
                        "start": start_s,
                        "end": end_s,
                        "snapshot_config_hash": snap_hash,
                        "completed_overlays": list(results.keys()),
                        "last_overlay": overlay_id,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )

    ranking = sorted(
        (
            {
                "overlay_id": oid,
                "rank_score": {
                    "promotion_ready": results[oid]["promotion"]["promotion_ready"],
                    "roi_pct": results[oid]["aggregate"]["overlay"].get("roi_pct"),
                    "picks": results[oid]["aggregate"]["overlay"].get("picks"),
                },
                **results[oid]["promotion"],
                "description": results[oid]["description"],
                "delta_vs_gate3_pp": (results[oid]["aggregate"].get("delta_overlay_vs_gate3") or {}).get(
                    "roi_change_pp"
                ),
                "delta_vs_gate7_pp": (results[oid]["aggregate"].get("delta_overlay_vs_gate7") or {}).get(
                    "roi_change_pp"
                ),
            }
            for oid in results
        ),
        key=_rank_key,
        reverse=True,
    )

    best = ranking[0]["overlay_id"] if ranking else None
    return {
        "start": start_s,
        "end": end_s,
        "snapshot_config_hash": snap_hash,
        "months_total": len(month_windows),
        "overlay_count": len(overlay_defs),
        "promotion_criteria": crit,
        "ranking": ranking,
        "best_overlay": best,
        "best_overlay_spec": results[best]["overlay_spec"] if best else None,
        "overlays": results,
        "message": (
            f"Sniper overlay sweep {start_s} → {end_s}: best={best} "
            f"roi={results[best]['aggregate']['overlay'].get('roi_pct') if best else None}% "
            f"promotion_ready={results[best]['promotion']['promotion_ready'] if best else False}."
        ),
    }
