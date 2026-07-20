"""Portfolio Kelly scaling for concurrent place picks."""

from __future__ import annotations

import math

import pandas as pd

from hibs_racing.place.kelly import place_kelly_fraction


def apply_portfolio_place_kelly(
    frame: pd.DataFrame,
    *,
    pct_col: str = "kelly_place_pct",
    race_col: str = "race_id",
    raw_col: str = "_kelly_raw",
    commission: float = 0.02,
    kelly_fraction: float = 0.25,
    max_runner_risk_pct: float = 0.02,
) -> pd.DataFrame:
    """
    Per-runner Kelly, then sqrt(n) downscale within each race for correlated legs.
  """
    if frame.empty:
        out = frame.copy()
        out[pct_col] = []
        return out

    out = frame.copy()
    raw: list[float] = []
    for _, row in out.iterrows():
        p = row.get("model_place_prob")
        o = row.get("place_decimal")
        try:
            p_f = float(p)
            o_f = float(o)
        except (TypeError, ValueError):
            raw.append(0.0)
            continue
        raw.append(
            place_kelly_fraction(
                p_f,
                o_f,
                commission=commission,
                kelly_fraction=kelly_fraction,
                max_runner_risk_pct=max_runner_risk_pct,
            )
        )
    out[raw_col] = raw

    scaled = []
    for _, group in out.groupby(race_col, sort=False):
        n = max(1, int((group[raw_col] > 0).sum()))
        factor = 1.0 / math.sqrt(n)
        scaled.extend((group[raw_col] * factor).tolist())
    out[pct_col] = [round(x * 100.0, 3) for x in scaled]
    return out.drop(columns=[raw_col], errors="ignore")
