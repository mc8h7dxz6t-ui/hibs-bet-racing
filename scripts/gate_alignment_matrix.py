#!/usr/bin/env python3
"""Build forensic gate alignment matrix from snapshot replay + walkforward reference."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hibs_racing.backtest.gate_config_alignment import (  # noqa: E402
    format_gate_matrix_table,
    merge_walkforward_reference,
    run_gate_alignment_matrix,
)
from hibs_racing.backtest.db_resolve import resolve_backtest_database  # noqa: E402


def _table_from_walkforward_only(wf_path: Path) -> dict:
    """When snapshot DB is empty, emit reference table from prior walkforward export."""
    wf = json.loads(wf_path.read_text(encoding="utf-8"))
    agg = wf.get("aggregate") or {}
    promo = wf.get("promotion_evaluation") or {}
    g3_roi = (agg.get("gate3") or {}).get("roi_pct")
    rows = []
    for lane_id, cat in (
        ("gate2", "canonical"),
        ("gate3", "canonical"),
        ("gate5", "canonical"),
        ("gate6", "canonical"),
        ("gate7", "canonical"),
        ("gate8", "canonical"),
    ):
        stats = agg.get(lane_id) or {}
        roi = stats.get("roi_pct")
        rows.append(
            {
                "lane_id": lane_id,
                "category": cat,
                "description": f"Walkforward reference ({wf.get('start')} → {wf.get('end')})",
                "picks": stats.get("picks"),
                "hit_rate": stats.get("hit_rate"),
                "roi_pct": roi,
                "pnl_units": stats.get("pnl_units"),
                "delta_vs_gate3_pp": (
                    (roi - g3_roi) if isinstance(roi, (int, float)) and isinstance(g3_roi, (int, float)) else None
                ),
                "volume_floor_pass": (promo.get(lane_id) or {}).get("volume_floor_pass"),
                "beats_gate3_roi": (promo.get(lane_id) or {}).get("beats_gate3_aggregate"),
            }
        )
    rows.sort(
        key=lambda r: (
            1 if r.get("beats_gate3_roi") else 0,
            float(r["roi_pct"]) if isinstance(r.get("roi_pct"), (int, float)) else -1e9,
        ),
        reverse=True,
    )
    return {
        "mode": "walkforward_reference_only",
        "source": str(wf_path),
        "window": f"{wf.get('start')} → {wf.get('end')}",
        "matrix": rows,
        "matrix_table_markdown": format_gate_matrix_table(rows),
        "note": "Snapshot DB empty — aligned overlays and blends require VPS replay.",
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Gate alignment forensic matrix")
    p.add_argument("--start", default="2025-11-01")
    p.add_argument("--end", default="2026-06-30")
    p.add_argument("--output", type=Path, default=ROOT / "exports" / "gate_alignment_matrix.json")
    p.add_argument(
        "--walkforward-ref",
        type=Path,
        default=ROOT / "exports" / "gate_lane_walkforward.json",
    )
    args = p.parse_args()

    try:
        db, db_reason = resolve_backtest_database()
        print(f"==> Using database: {db} ({db_reason})", file=sys.stderr)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        db = None

    report = run_gate_alignment_matrix(
        start=args.start,
        end=args.end,
        database=db,
    )
    if report.get("error"):
        wf = args.walkforward_ref
        if wf.is_file():
            report = _table_from_walkforward_only(wf)
        else:
            print(json.dumps(report, indent=2))
            return 1
    else:
        report = merge_walkforward_reference(report, args.walkforward_ref)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    md_path = args.output.with_suffix(".md")
    md_path.write_text(report.get("matrix_table_markdown", ""), encoding="utf-8")
    print(report.get("matrix_table_markdown", json.dumps(report, indent=2)))
    print(f"\nWrote {args.output} and {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
