#!/usr/bin/env python3
"""Benchmark production vs tweak configs on snapshot replay (no full rescore)."""
from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path

# repo root on path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hibs_racing.backtest.gate_benchmark import _apply_gate_flags, _delta, _settle
from hibs_racing.backtest.snapshot_store import load_snapshots, scoring_config_hash
from hibs_racing.config import db_path, load_config


def _lane_stats(frame, flag: str) -> dict:
    return _settle(frame, flag)


def run(*, start: str, end: str, out: Path | None) -> dict:
    cfg = load_config()
    db = db_path(cfg)
    paper = cfg.get("paper", {})
    snap = load_snapshots(db, start, end, config_hash=scoring_config_hash(paper))
    if snap.empty:
        return {"error": "no snapshots", "start": start, "end": end}

    variants = {
        "production": deepcopy(paper),
        "tweak_looser_gate2": deepcopy(paper),
        "tweak_tighter_ev": deepcopy(paper),
        "gate1_only_live_style": deepcopy(paper),
    }
    variants["tweak_looser_gate2"]["gate2"] = {
        **variants["tweak_looser_gate2"].get("gate2", {}),
        "enabled": True,
        "min_confidence": 0.50,
        "max_value_per_meeting": 8,
        "max_value_per_race": 3,
    }
    variants["tweak_tighter_ev"]["min_place_ev"] = 0.06
    variants["tweak_tighter_ev"]["min_combo_bayes_place"] = 0.24
    g2 = variants["tweak_tighter_ev"].setdefault("gate2", {})
    if isinstance(g2, dict):
        g2["min_confidence"] = 0.58

    variants["gate1_only_live_style"]["gate2"] = {
        **variants["gate1_only_live_style"].get("gate2", {}),
        "enabled": False,
    }

    report: dict = {
        "start": start,
        "end": end,
        "runners": len(snap),
        "card_days": int(snap["card_date"].nunique()),
        "config_hash": scoring_config_hash(paper),
        "variants": {},
    }
    none_stats = None
    for name, pcfg in variants.items():
        gated = _apply_gate_flags(snap, pcfg)
        gated = gated[gated["finish_pos"].notna()].copy()
        prod = _lane_stats(gated, "flag_production")
        if none_stats is None:
            none_stats = _lane_stats(gated, "flag_none")
        blocked = (
            gated.loc[gated["flag_none"].eq(1) & gated["flag_production"].eq(0), "production_reason"]
            .dropna()
            .astype(str)
            .value_counts()
            .head(10)
            .to_dict()
        )
        report["variants"][name] = {
            "stats": prod,
            "delta_vs_none": _delta(prod, none_stats),
            "blocked_top": blocked,
        }

    payload = json.dumps(report, indent=2)
    print(payload)
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(payload, encoding="utf-8")
    return report


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--start", default="2024-03-15")
    p.add_argument("--end", default="2026-05-22")
    p.add_argument("--output", type=Path, default=ROOT / "exports" / "config_variant_benchmark.json")
    args = p.parse_args()
    run(start=args.start, end=args.end, out=args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
