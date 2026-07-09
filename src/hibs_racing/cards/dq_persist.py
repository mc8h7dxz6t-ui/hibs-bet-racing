"""Racing card store — persist only when runner data quality improves."""

from __future__ import annotations

import os
from typing import Any, Dict, List

import pandas as pd

from hibs_racing.cards.data_quality import runner_data_quality_pct


def preserve_best_dq_enabled() -> bool:
    return (os.getenv("HIBS_RACING_PRESERVE_BEST_DQ") or "1").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _is_empty(val: Any) -> bool:
    if val is None:
        return True
    try:
        if pd.isna(val):
            return True
    except (TypeError, ValueError):
        pass
    if isinstance(val, str) and not val.strip():
        return True
    return False


def merge_runners_preserve_best(existing: pd.DataFrame, incoming: pd.DataFrame) -> pd.DataFrame:
    """Keep higher-DQ runner rows; fill nulls from the weaker side when tied."""
    if existing.empty:
        return incoming.copy()
    if incoming.empty:
        return existing.copy()

    by_id: Dict[str, Dict[str, Any]] = {
        str(r.get("runner_id")): dict(r) for r in existing.to_dict(orient="records") if r.get("runner_id")
    }
    out_rows: List[Dict[str, Any]] = []
    seen: set[str] = set()

    for rec in incoming.to_dict(orient="records"):
        rid = str(rec.get("runner_id") or "")
        if not rid:
            out_rows.append(rec)
            continue
        seen.add(rid)
        old = by_id.get(rid)
        if not old:
            out_rows.append(rec)
            continue
        old_dq = runner_data_quality_pct(old)
        new_dq = runner_data_quality_pct(rec)
        if old_dq > new_dq:
            merged = dict(old)
            for key, val in rec.items():
                if _is_empty(merged.get(key)) and not _is_empty(val):
                    merged[key] = val
            out_rows.append(merged)
        else:
            merged = dict(rec)
            for key, val in old.items():
                if _is_empty(merged.get(key)) and not _is_empty(val):
                    merged[key] = val
            out_rows.append(merged)

    for rid, old in by_id.items():
        if rid not in seen:
            out_rows.append(old)

    return pd.DataFrame(out_rows)


def mean_runner_dq(frame: pd.DataFrame) -> float:
    if frame.empty:
        return 0.0
    dqs = [runner_data_quality_pct(row) for row in frame.to_dict(orient="records")]
    scored = [d for d in dqs if d > 0]
    return round(sum(scored) / len(scored), 1) if scored else 0.0
