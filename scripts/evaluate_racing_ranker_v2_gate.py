#!/usr/bin/env python3
"""Evaluate racing ranker v2 promotion gate (28d paper place ROI)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Racing ranker v2 promotion gate")
    parser.add_argument("--min-days", type=int, default=None)
    parser.add_argument("--min-samples", type=int, default=200)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--require-promote", action="store_true")
    args = parser.parse_args()

    from hibs_racing.engine_adapter_promotion import evaluate_racing_ranker_v2_gate

    report = evaluate_racing_ranker_v2_gate(
        min_shadow_days=args.min_days,
        min_samples=args.min_samples,
    )
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(
            f"promote={report.get('promote')} reason={report.get('reason')} "
            f"horses={report.get('horse_form_horses')} n_settled={report.get('n_settled')} "
            f"mean_roi={report.get('mean_place_roi_paper')}"
        )
    if args.require_promote and not report.get("promote"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
