from __future__ import annotations

import re

import pandas as pd

_CLASS_RE = re.compile(r"class\s*(\d+)", re.I)


def parse_class_num(value: object) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    if not text:
        return None
    match = _CLASS_RE.search(text)
    if match:
        return float(match.group(1))
    try:
        return float(text)
    except ValueError:
        return None


def bayesian_rate(
    successes: pd.Series,
    trials: pd.Series,
    *,
    global_rate: float,
    alpha: float,
) -> pd.Series:
    """Smoothed rate: (successes + alpha * global) / (trials + alpha)."""
    return (successes + alpha * global_rate) / (trials + alpha)


def add_point_in_time_combo_stats(
    frame: pd.DataFrame,
    *,
    alpha: float = 8.0,
    place_cutoff: int = 3,
) -> pd.DataFrame:
    """
    Trainer–jockey joint stats using only rides BEFORE each runner's race (no leakage).
    """
    out = frame.copy()
    out["jockey"] = out["jockey"].fillna("").astype(str).str.strip()
    out["trainer"] = out["trainer"].fillna("").astype(str).str.strip()
    out["pair_key"] = out["jockey"] + "||" + out["trainer"]

    out = out.sort_values(["race_date", "race_id", "runner_id"]).reset_index(drop=True)
    out["finish_pos"] = pd.to_numeric(out["finish_pos"], errors="coerce")
    out["win"] = (out["finish_pos"] == 1).astype(int)
    out["placed"] = (out["finish_pos"] <= place_cutoff).astype(int)

    global_win = out["win"].mean() if len(out) else 0.1
    global_place = out["placed"].mean() if len(out) else 0.3

    grouped = out.groupby("pair_key", sort=False)
    out["combo_prior_rides"] = grouped.cumcount()
    out["combo_prior_wins"] = grouped["win"].cumsum().shift(1).fillna(0)
    out["combo_prior_places"] = grouped["placed"].cumsum().shift(1).fillna(0)

    out["combo_bayes_win"] = bayesian_rate(
        out["combo_prior_wins"], out["combo_prior_rides"], global_rate=global_win, alpha=alpha
    )
    out["combo_bayes_place"] = bayesian_rate(
        out["combo_prior_places"], out["combo_prior_rides"], global_rate=global_place, alpha=alpha
    )
    return out
