"""Stratified par-time baseline and speed figure delta."""

from __future__ import annotations

from typing import Any

import pandas as pd

from hibs_racing.features.wfa import adjusted_beaten_lengths, wfa_allowance_lbs


def distance_band(distance_f: float | None) -> str:
    if distance_f is None:
        return "unknown"
    d = float(distance_f)
    if d <= 7.0:
        return "sprint"
    if d <= 9.0:
        return "mile"
    if d <= 12.0:
        return "middle"
    return "staying"


def class_band(race_class: Any) -> str:
    text = str(race_class or "").strip().lower()
    digits = "".join(c for c in text if c.isdigit())
    if not digits:
        return "unknown"
    try:
        c = int(digits[0])
    except ValueError:
        return "unknown"
    if c <= 2:
        return "class_1_2"
    if c <= 4:
        return "class_3_4"
    if c <= 6:
        return "class_5_6"
    return "class_7_plus"


def stratify_key(row: pd.Series) -> str:
    course = str(row.get("course") or "").strip().lower()
    date = str(row.get("race_date") or "")[:10]
    rtype = str(row.get("race_type") or "flat").lower()
    return "|".join(
        [
            course,
            date,
            rtype,
            distance_band(row.get("distance_f")),
            class_band(row.get("race_class")),
        ]
    )


def wfa_adjusted_race_time(row: pd.Series) -> float | None:
    secs = row.get("race_time_secs")
    if secs is None or (isinstance(secs, float) and pd.isna(secs)):
        return None
    try:
        t = float(secs)
    except (TypeError, ValueError):
        return None
    allowance = wfa_allowance_lbs(
        distance_f=row.get("distance_f"),
        age=int(row["age"]) if pd.notna(row.get("age")) else None,
        race_date=str(row.get("race_date") or ""),
    )
    lbs = row.get("weight_lbs")
    if lbs is not None and not (isinstance(lbs, float) and pd.isna(lbs)):
        # Add allowance seconds proxy: ~0.05s per lb under WfA
        t += 0.05 * (float(lbs) - allowance)
    return t


def compute_speed_deltas(frame: pd.DataFrame) -> pd.DataFrame:
    """
    Card-relative stratified par baseline → speed_figure_delta per runner.
    Requires race_time_secs (or derives from missing with btn fallback).
    """
    out = frame.copy()
    if "race_time_secs" not in out.columns:
        out["race_time_secs"] = pd.NA
    out["wfa_adjusted_time"] = out.apply(wfa_adjusted_race_time, axis=1)
    out["stratify_key"] = out.apply(stratify_key, axis=1)

    if "beaten_lengths" not in out.columns:
        out["beaten_lengths"] = pd.NA
    if "margin_to_next" not in out.columns:
        out["margin_to_next"] = pd.NA
    if out["beaten_lengths"].isna().all() and out["margin_to_next"].notna().any():
        out["beaten_lengths"] = out["margin_to_next"]

    # par = median adjusted time per stratify bucket on this card/day
    par = (
        out.dropna(subset=["wfa_adjusted_time"])
        .groupby("stratify_key", as_index=False)["wfa_adjusted_time"]
        .median()
        .rename(columns={"wfa_adjusted_time": "par_time_secs"})
    )
    out = out.merge(par, on="stratify_key", how="left")
    out["speed_figure_delta"] = out["par_time_secs"] - out["wfa_adjusted_time"]

    # btn-based fallback when time missing
    mask = out["speed_figure_delta"].isna() & out["beaten_lengths"].notna()
    if mask.any():

        def _btn_delta(r: pd.Series) -> float | None:
            allowance = wfa_allowance_lbs(
                distance_f=r.get("distance_f"),
                age=int(r["age"]) if pd.notna(r.get("age")) else None,
                race_date=str(r.get("race_date") or ""),
            )
            adj = adjusted_beaten_lengths(
                r.get("beaten_lengths"),
                weight_carried=r.get("weight_lbs"),
                allowance_lbs=allowance,
            )
            if adj is None:
                return None
            return -float(adj)

        out.loc[mask, "speed_figure_delta"] = out.loc[mask].apply(_btn_delta, axis=1)

    return out
