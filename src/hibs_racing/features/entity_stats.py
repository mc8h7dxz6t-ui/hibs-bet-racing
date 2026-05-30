from __future__ import annotations

import numpy as np
import pandas as pd

from hibs_racing.features.combo_stats import bayesian_rate


def _normalize_entity(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.strip()


def _prepare_outcomes(frame: pd.DataFrame, *, place_cutoff: int) -> pd.DataFrame:
    out = frame.copy()
    if "win" not in out.columns or "placed" not in out.columns:
        out["finish_pos"] = pd.to_numeric(out.get("finish_pos"), errors="coerce")
        out["win"] = (out["finish_pos"] == 1).astype(int)
        out["placed"] = (out["finish_pos"] <= place_cutoff).astype(int)
    return out


def add_point_in_time_entity_stats(
    frame: pd.DataFrame,
    *,
    entity_col: str,
    prefix: str,
    alpha: float = 8.0,
    place_cutoff: int = 3,
) -> pd.DataFrame:
    """Expanding jockey/trainer (yard proxy) priors — prior rides only, no leakage."""
    out = _prepare_outcomes(frame, place_cutoff=place_cutoff)
    key = f"_{prefix}_key"
    out[key] = _normalize_entity(out.get(entity_col, ""))
    out = out.sort_values(["race_date", "race_id", "runner_id"]).reset_index(drop=True)

    global_win = out["win"].mean() if len(out) else 0.1
    global_place = out["placed"].mean() if len(out) else 0.3

    grouped = out.groupby(key, sort=False)
    out[f"{prefix}_prior_rides"] = grouped.cumcount()
    out[f"{prefix}_prior_wins"] = grouped["win"].cumsum().shift(1).fillna(0)
    out[f"{prefix}_prior_places"] = grouped["placed"].cumsum().shift(1).fillna(0)

    out[f"{prefix}_bayes_win"] = bayesian_rate(
        out[f"{prefix}_prior_wins"],
        out[f"{prefix}_prior_rides"],
        global_rate=global_win,
        alpha=alpha,
    )
    out[f"{prefix}_bayes_place"] = bayesian_rate(
        out[f"{prefix}_prior_places"],
        out[f"{prefix}_prior_rides"],
        global_rate=global_place,
        alpha=alpha,
    )
    return out.drop(columns=[key], errors="ignore")


def _rolling_entity_window(
    frame: pd.DataFrame,
    *,
    entity_col: str,
    prefix: str,
    window_days: int,
    suffix: str,
    place_cutoff: int,
) -> pd.DataFrame:
    """Place strike rate in the last N calendar days (prior rides only)."""
    out = _prepare_outcomes(frame, place_cutoff=place_cutoff)
    key = f"_{prefix}_key"
    out[key] = _normalize_entity(out.get(entity_col, ""))
    out["_dt"] = pd.to_datetime(out["race_date"], errors="coerce")
    out = out.sort_values(["race_date", "race_id", "runner_id"]).reset_index(drop=True)

    col_rides = f"{prefix}_rides_{suffix}"
    col_rate = f"{prefix}_place_{suffix}"
    out[col_rides] = 0
    out[col_rate] = np.nan

    for _entity, grp in out.groupby(key, sort=False):
        if grp.empty:
            continue
        dates = grp["_dt"].to_numpy()
        placed = grp["placed"].to_numpy()
        er = np.zeros(len(grp), dtype=int)
        erate = np.full(len(grp), np.nan)
        for i in range(len(grp)):
            if i == 0 or pd.isna(dates[i]):
                continue
            prior_dates = dates[:i]
            prior_placed = placed[:i]
            valid = ~pd.isna(prior_dates)
            if not valid.any():
                continue
            cutoff = dates[i] - np.timedelta64(window_days, "D")
            mask = valid & (prior_dates >= cutoff)
            er[i] = int(mask.sum())
            if er[i] > 0:
                erate[i] = float(prior_placed[mask].mean())
        out.loc[grp.index, col_rides] = er
        out.loc[grp.index, col_rate] = erate

    return out.drop(columns=[key, "_dt"], errors="ignore")


def add_entity_rolling_place_rates(
    frame: pd.DataFrame,
    *,
    entity_col: str,
    prefix: str,
    windows: tuple[int, ...] = (14, 90),
    place_cutoff: int = 3,
) -> pd.DataFrame:
    out = frame.copy()
    for days in windows:
        out = _rolling_entity_window(
            out,
            entity_col=entity_col,
            prefix=prefix,
            window_days=days,
            suffix=f"{days}d",
            place_cutoff=place_cutoff,
        )
    return out


def add_entity_consistency(
    frame: pd.DataFrame,
    *,
    entity_col: str,
    prefix: str,
    window_rides: int = 10,
    place_cutoff: int = 3,
) -> pd.DataFrame:
    """
    Consistency = 1 − std(placed) over last N prior rides (higher = steadier place profile).
    """
    out = _prepare_outcomes(frame, place_cutoff=place_cutoff)
    key = f"_{prefix}_key"
    out[key] = _normalize_entity(out.get(entity_col, ""))
    out = out.sort_values(["race_date", "race_id", "runner_id"]).reset_index(drop=True)
    out[f"{prefix}_consistency"] = np.nan

    for _entity, grp in out.groupby(key, sort=False):
        placed = grp["placed"].to_numpy()
        vals = np.full(len(grp), np.nan)
        for i in range(len(grp)):
            if i == 0:
                continue
            start = max(0, i - window_rides)
            window = placed[start:i]
            if len(window) >= 3:
                vals[i] = 1.0 - float(np.std(window))
        out.loc[grp.index, f"{prefix}_consistency"] = vals

    return out.drop(columns=[key], errors="ignore")


def add_all_entity_stats(
    frame: pd.DataFrame,
    *,
    alpha: float = 8.0,
    place_cutoff: int = 3,
) -> pd.DataFrame:
    """Jockey + trainer (yard proxy) point-in-time stats, rolling form, consistency."""
    out = frame.copy()
    for entity_col, prefix in (("jockey", "jockey"), ("trainer", "trainer")):
        out = add_point_in_time_entity_stats(
            out, entity_col=entity_col, prefix=prefix, alpha=alpha, place_cutoff=place_cutoff
        )
        out = add_entity_rolling_place_rates(
            out, entity_col=entity_col, prefix=prefix, place_cutoff=place_cutoff
        )
        out = add_entity_consistency(
            out, entity_col=entity_col, prefix=prefix, place_cutoff=place_cutoff
        )

    for prefix in ("jockey", "trainer"):
        bayes = f"{prefix}_bayes_place"
        for suffix in ("14d", "90d"):
            rate_col = f"{prefix}_place_{suffix}"
            if rate_col in out.columns:
                out[rate_col] = out[rate_col].fillna(out[bayes])
        out[f"{prefix}_consistency"] = out[f"{prefix}_consistency"].fillna(0.5)
    return out
