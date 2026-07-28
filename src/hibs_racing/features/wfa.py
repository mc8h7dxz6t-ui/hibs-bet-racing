"""Weight-for-Age (WfA) normalization — upstream of speed figure delta."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

_WFA_PATH = Path(__file__).resolve().parents[3] / "data" / "wfa_table.json"


def _load_wfa() -> dict[str, Any]:
    if not _WFA_PATH.is_file():
        return {"bands": [], "default_allowance_lbs": 0}
    return json.loads(_WFA_PATH.read_text(encoding="utf-8"))


def wfa_allowance_lbs(
    *,
    distance_f: float | None,
    age: int | None,
    race_date: str | None,
) -> float:
    """Lookup simplified BHA WfA allowance in lbs."""
    cfg = _load_wfa()
    default = float(cfg.get("default_allowance_lbs") or 0)
    if distance_f is None or age is None or not race_date:
        return default
    try:
        month = datetime.strptime(str(race_date)[:10], "%Y-%m-%d").month
    except ValueError:
        return default
    summer = month >= 4 and month <= 10
    target_month = 7 if summer else 1
    dist = float(distance_f)
    for band in cfg.get("bands") or []:
        if not isinstance(band, dict):
            continue
        if int(band.get("age") or 0) != int(age):
            continue
        if int(band.get("month") or 0) != target_month:
            continue
        if dist < float(band.get("min_f") or 0):
            continue
        if dist > float(band.get("max_f") or 99):
            continue
        return float(band.get("allowance_lbs") or default)
    return default


def adjusted_weight_lbs(weight_carried: float | None, allowance: float) -> float | None:
    if weight_carried is None:
        return None
    return float(weight_carried) + float(allowance)


def adjusted_beaten_lengths(
    raw_btn: float | None,
    *,
    weight_carried: float | None,
    allowance_lbs: float,
) -> float | None:
    """Normalize beaten lengths for WfA — lighter carried weight tightens margin."""
    if raw_btn is None:
        return None
    btn = float(raw_btn)
    if weight_carried is None:
        return btn
    # ~0.25 lengths per lb vs WfA benchmark (institutional approximation)
    return btn - 0.25 * (float(weight_carried) - allowance_lbs)
