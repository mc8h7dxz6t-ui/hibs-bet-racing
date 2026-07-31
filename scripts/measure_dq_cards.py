#!/usr/bin/env python3
"""Measure racing card DQ distribution — mirrors football measure_dq_7d.py."""

from __future__ import annotations

import json
import os
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    from hibs_racing.cards.data_quality import runner_data_quality_pct, runner_quality_blocks
    from hibs_racing.cards.dq_persist import mean_runner_dq
    from hibs_racing.cards.query import load_scored_cards
    from hibs_racing.data_quality_targets import racing_data_quality_target_pct

    target = racing_data_quality_target_pct()
    frame = load_scored_cards()
    if frame.empty:
        print(json.dumps({"ok": False, "message": "no_scored_cards", "target_pct": target}))
        return 1

    dqs: list[int] = []
    block_gaps: Counter = Counter()
    thin_by_course: Counter = Counter()
    for _, row in frame.iterrows():
        d = row.to_dict()
        dq = runner_data_quality_pct(d)
        dqs.append(dq)
        if dq < target:
            thin_by_course[str(d.get("course") or "?")] += 1
            for block_id, block in runner_quality_blocks(d).items():
                if block.get("skipped"):
                    continue
                if int(block.get("pct") or 0) < 100:
                    for miss in block.get("missing") or []:
                        block_gaps[f"{block_id}:{miss}"] += 1

    g90 = sum(1 for d in dqs if d >= 90)
    g95 = sum(1 for d in dqs if d >= 95)
    mean = mean_runner_dq(frame)
    card_dates = sorted(frame["card_date"].astype(str).str[:10].unique().tolist()) if "card_date" in frame.columns else []
    report = {
        "ok": mean >= target,
        "target_pct": target,
        "card_dates": card_dates,
        "runner_count": len(dqs),
        "mean_dq_pct": mean,
        "dq_gte_90": g90,
        "dq_gte_95": g95,
        "pct_gte_95": round(100.0 * g95 / max(1, len(dqs)), 1),
        "top_block_gaps": block_gaps.most_common(12),
        "thin_by_course": thin_by_course.most_common(8),
    }
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
