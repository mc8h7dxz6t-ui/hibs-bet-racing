#!/usr/bin/env python3
"""Extended walkforward backtest for gate9–gate11 blend lanes (+ gate2–gate8 baseline)."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd

from hibs_racing.backtest.gate_benchmark import _historical_bounds, backfill_scored_snapshots
from hibs_racing.backtest.gate_impact import BLEND_LANES, WALKFORWARD_FOCUS_LANES, run_gate_impact, run_gate_lane_walkforward
from hibs_racing.backtest.snapshot_store import upsert_snapshots
from hibs_racing.config import db_path, load_config
from hibs_racing.features.store import init_db


def _seed_demo_snapshots(db: Path, start: str, end: str) -> int:
    """Seed multi-month synthetic snapshots for pipeline validation (not production ROI)."""
    init_db(db)
    months = pd.period_range(start=start, end=end, freq="M")
    total = 0
    for period in months:
        for day in (5, 15, 25):
            card_date = f"{period.year}-{period.month:02d}-{day:02d}"
            if card_date < start or card_date > end:
                continue
            rows = []
            for race_idx in range(4):
                race_id = f"{card_date}-race{race_idx}"
                for runner_idx in range(8):
                    orating = 40 + runner_idx * 8 + race_idx * 2
                    win_dec = 2.5 + runner_idx * 1.4 + race_idx * 0.3
                    rows.append(
                        {
                            "runner_id": f"{card_date}-r{race_idx}-{runner_idx}",
                            "race_id": race_id,
                            "course": "Ascot" if race_idx % 2 == 0 else "York",
                            "race_name": "Class 4 Handicap",
                            "field_size": 10,
                            "official_rating": orating,
                            "win_decimal": win_dec,
                            "place_fraction": 0.25,
                            "places": 3,
                            "model_score": 0.95 - runner_idx * 0.04,
                            "model_win_prob": 0.18 + runner_idx * 0.02,
                            "model_place_prob": 0.28 + runner_idx * 0.03,
                            "combo_bayes_place": 0.24 + runner_idx * 0.02,
                            "place_ev": 0.05 + runner_idx * 0.01,
                            "ew_combined_ev": 0.07 + runner_idx * 0.012,
                            "flag_raw": 1,
                            "trainer_rtf": 8.0 + runner_idx * 4,
                            "horse_course_win_rate": 0.15,
                            "enrich_source": "demo_seed",
                        }
                    )
            frame = pd.DataFrame(rows)
            finish = {r["runner_id"]: 1 if i % 5 == 0 else 4 for i, r in enumerate(rows)}
            total += upsert_snapshots(db, card_date, frame, finish_by_runner=finish)
    return total


def _lane_table(report: dict) -> str:
    agg = report.get("aggregate") or {}
    g3_roi = (agg.get("gate3") or {}).get("roi_pct")
    lines = [
        "# Extended gate walkforward",
        "",
        f"Window: **{report.get('start')} → {report.get('end')}**",
        f"Months with data: {report.get('months_with_data')} / {report.get('months_total')}",
        "",
        "| Lane | Picks | Hit% | ROI% | PnL units | vs G3 (pp) |",
        "|---|--:|--:|--:|--:|--:|",
    ]
    focus = list(WALKFORWARD_FOCUS_LANES) + [f"gate{n}" for n in (9, 10, 11) if f"gate{n}" not in WALKFORWARD_FOCUS_LANES]
    seen: set[str] = set()
    for lane in focus:
        if lane in seen:
            continue
        seen.add(lane)
        stats = agg.get(lane) or {}
        picks = int(stats.get("picks") or 0)
        hit = stats.get("hit_rate")
        roi = stats.get("roi_pct")
        pnl = stats.get("pnl_units")
        hit_s = f"{100 * hit:.1f}" if isinstance(hit, (int, float)) else "—"
        roi_s = f"{roi:.1f}" if isinstance(roi, (int, float)) else "—"
        pnl_s = f"{pnl:.1f}" if isinstance(pnl, (int, float)) else "—"
        dpp = None
        if isinstance(roi, (int, float)) and isinstance(g3_roi, (int, float)):
            dpp = roi - g3_roi
        dpp_s = f"{dpp:+.1f}" if isinstance(dpp, (int, float)) else "—"
        marker = " **" if lane in BLEND_LANES else ""
        lines.append(f"| {lane}{marker} | {picks} | {hit_s} | {roi_s} | {pnl_s} | {dpp_s} |")
    lines.append("")
    if BLEND_LANES:
        lines.append(f"** = new blend lane ({', '.join(BLEND_LANES)})")
        lines.append("")
    promo = report.get("promotion_evaluation") or {}
    for lane in BLEND_LANES:
        row = promo.get(lane) or {}
        if row:
            lines.append(
                f"- **{lane}**: promotion_ready={row.get('promotion_ready')} "
                f"roi={row.get('aggregate_roi_pct')}% beats_g3={row.get('beats_gate3_aggregate')}"
            )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Extended gate walkforward (gate9–11 + focus lanes)")
    parser.add_argument("--start", default="2025-11-01")
    parser.add_argument("--end", default="2026-07-31")
    parser.add_argument("--database", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=ROOT / "exports" / "gate_lane_walkforward_extended.json")
    parser.add_argument("--impact-output", type=Path, default=ROOT / "exports" / "gate_impact_extended.json")
    parser.add_argument("--seed-demo", action="store_true", help="Seed synthetic snapshots (pipeline check only)")
    parser.add_argument("--backfill", action="store_true", help="Backfill snapshots from runners before replay")
    parser.add_argument("--force-backfill", action="store_true")
    args = parser.parse_args()

    cfg = load_config()
    db = args.database or db_path(cfg)
    start_s = args.start
    end_s = args.end

    if args.seed_demo:
        n = _seed_demo_snapshots(db, start_s, end_s)
        print(f"Seeded {n} demo snapshot rows into {db}")

    if args.backfill:
        bf = backfill_scored_snapshots(
            start=start_s,
            end=end_s,
            database=db,
            force=args.force_backfill,
        )
        print(json.dumps(bf, indent=2))
        if int(bf.get("rows_written") or 0) == 0 and bf.get("message") == "No historical cards.":
            print("No runners to backfill — use VPS DB or --seed-demo", file=sys.stderr)

    max_start, max_end = _historical_bounds(db)
    if max_start and max_end:
        if start_s < max_start:
            start_s = max_start
        if end_s > max_end:
            end_s = max_end
        print(f"Historical bounds clipped to {start_s} → {end_s}")

    progress = args.output.with_name("gate_lane_walkforward_extended_progress.json")
    report = run_gate_lane_walkforward(
        start=start_s,
        end=end_s,
        database=db,
        progress_path=progress,
    )
    if report.get("error"):
        print(json.dumps(report, indent=2))
        return 1

    impact = run_gate_impact(start=start_s, end=end_s, database=db)
    report["gate_impact"] = {
        "lanes": impact.get("lanes"),
        "comparisons": impact.get("comparisons"),
    }
    report["blend_lanes"] = list(BLEND_LANES)
    report["generated_on"] = date.today().isoformat()
    if args.seed_demo:
        report["data_source"] = "synthetic_demo_seed"
        report["note"] = "Demo seed only — run on VPS feature_store.sqlite for production ROI."

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    args.impact_output.write_text(json.dumps(impact, indent=2), encoding="utf-8")

    md_path = args.output.with_suffix(".md")
    md_path.write_text(_lane_table(report), encoding="utf-8")

    print(report.get("message", "done"))
    print(_lane_table(report))
    print(f"\nWrote {args.output}")
    print(f"Wrote {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
