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


def apply_portfolio_ew_kelly(
    frame: pd.DataFrame,
    *,
    pct_col: str = "kelly_ew_pct",
    race_col: str = "race_id",
    raw_col: str = "_kelly_ew_raw",
    kelly_fraction: float = 0.25,
    max_runner_risk_pct: float = 0.02,
) -> pd.DataFrame:
    """Per-runner EW Kelly, then sqrt(n) downscale within each race."""
    if frame.empty:
        out = frame.copy()
        out[pct_col] = []
        return out

    from hibs_racing.place.ew_ev import EachWayQuote
    from hibs_racing.place.ew_kelly import each_way_kelly_fraction

    out = frame.copy()
    raw: list[float] = []
    for _, row in out.iterrows():
        win = row.get("win_decimal")
        if win is None or (isinstance(win, float) and pd.isna(win)):
            raw.append(0.0)
            continue
        try:
            quote = EachWayQuote(
                win_decimal=float(win),
                place_fraction=float(row.get("place_fraction") or 0.25),
                places=int(row.get("places") or 3),
            )
            raw.append(
                each_way_kelly_fraction(
                    float(row["model_win_prob"]),
                    float(row["model_place_prob"]),
                    quote,
                    kelly_fraction=kelly_fraction,
                    max_runner_risk_pct=max_runner_risk_pct,
                )
            )
        except (TypeError, ValueError):
            raw.append(0.0)
    out[raw_col] = raw

    scaled = []
    for _, group in out.groupby(race_col, sort=False):
        n = max(1, int((group[raw_col] > 0).sum()))
        factor = 1.0 / math.sqrt(n)
        scaled.extend((group[raw_col] * factor).tolist())
    out[pct_col] = [round(x * 100.0, 3) for x in scaled]
    return out.drop(columns=[raw_col], errors="ignore")
