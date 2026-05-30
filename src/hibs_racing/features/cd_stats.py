from __future__ import annotations

import numpy as np
import pandas as pd

from hibs_racing.entity.natural_key import normalize_course
from hibs_racing.features.combo_stats import bayesian_rate


def distance_bucket(distance_f: object) -> str:
    """UK flat bands: sprint ≤6f, mile 6–8f, middle 8–12f, staying 12f+."""
    if distance_f is None or (isinstance(distance_f, float) and np.isnan(distance_f)):
        return "unknown"
    try:
        d = float(distance_f)
    except (TypeError, ValueError):
        return "unknown"
    if d <= 0:
        return "unknown"
    if d <= 6.0:
        return "sprint"
    if d <= 8.0:
        return "mile"
    if d <= 12.0:
        return "middle"
    return "staying"


def attach_cd_keys(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["jockey"] = out.get("jockey", "").fillna("").astype(str).str.strip()
    out["trainer"] = out.get("trainer", "").fillna("").astype(str).str.strip()
    out["course_slug"] = out.get("course", "").map(lambda c: normalize_course(c) or "unknown")
    out["dist_bucket"] = pd.to_numeric(out.get("distance_f"), errors="coerce").map(distance_bucket)

    out["_jockey_cd_key"] = out["jockey"] + "||" + out["course_slug"]
    out["_trainer_cd_key"] = out["trainer"] + "||" + out["course_slug"]
    out["_combo_cd_key"] = out["jockey"] + "||" + out["trainer"] + "||" + out["course_slug"]
    out["_jockey_cdd_key"] = out["_jockey_cd_key"] + "||" + out["dist_bucket"]
    out["_trainer_cdd_key"] = out["_trainer_cd_key"] + "||" + out["dist_bucket"]
    out["_combo_cdd_key"] = out["_combo_cd_key"] + "||" + out["dist_bucket"]
    return out


def _prepare_outcomes(frame: pd.DataFrame, *, place_cutoff: int) -> pd.DataFrame:
    out = frame.copy()
    out["finish_pos"] = pd.to_numeric(out.get("finish_pos"), errors="coerce")
    out["win"] = (out["finish_pos"] == 1).astype(int)
    out["placed"] = (out["finish_pos"] <= place_cutoff).astype(int)
    return out


def _add_pit_place_stats(
    frame: pd.DataFrame,
    *,
    key_col: str,
    prefix: str,
    alpha: float,
    global_place: float,
) -> pd.DataFrame:
    grouped = frame.groupby(key_col, sort=False)
    frame[f"{prefix}_prior_rides"] = grouped.cumcount()
    frame[f"{prefix}_prior_places"] = grouped["placed"].cumsum().shift(1).fillna(0)
    frame[f"{prefix}_bayes_place"] = bayesian_rate(
        frame[f"{prefix}_prior_places"],
        frame[f"{prefix}_prior_rides"],
        global_rate=global_place,
        alpha=alpha,
    )
    return frame


def add_all_cd_stats(
    frame: pd.DataFrame,
    *,
    alpha: float = 8.0,
    place_cutoff: int = 3,
) -> pd.DataFrame:
    """
    Point-in-time course/distance (CD) priors — jockey, trainer, and pair at course
    and at course+distance bucket.
    """
    if frame.empty:
        return frame

    out = attach_cd_keys(frame)
    out = _prepare_outcomes(out, place_cutoff=place_cutoff)
    out = out.sort_values(["race_date", "race_id", "runner_id"]).reset_index(drop=True)

    global_place = out["placed"].mean() if len(out) else 0.3

    pit_specs = (
        ("_jockey_cd_key", "jockey_cd"),
        ("_trainer_cd_key", "trainer_cd"),
        ("_combo_cd_key", "combo_cd"),
        ("_jockey_cdd_key", "jockey_cdd"),
        ("_trainer_cdd_key", "trainer_cdd"),
        ("_combo_cdd_key", "combo_cdd"),
    )
    for key_col, prefix in pit_specs:
        out = _add_pit_place_stats(out, key_col=key_col, prefix=prefix, alpha=alpha, global_place=global_place)

    # Back-fill sparse CD with entity-level place rates when available
    for cd_prefix, entity_prefix in (
        ("jockey_cd", "jockey"),
        ("trainer_cd", "trainer"),
        ("combo_cd", "combo"),
        ("jockey_cdd", "jockey"),
        ("trainer_cdd", "trainer"),
        ("combo_cdd", "combo"),
    ):
        bayes_col = f"{cd_prefix}_bayes_place"
        fallback = f"{entity_prefix}_bayes_place"
        if bayes_col in out.columns and fallback in out.columns:
            sparse = out[f"{cd_prefix}_prior_rides"] < 2
            out.loc[sparse, bayes_col] = out.loc[sparse, bayes_col].fillna(out.loc[sparse, fallback])
        elif bayes_col in out.columns:
            out[bayes_col] = out[bayes_col].fillna(global_place)

    drop_cols = [c for c in out.columns if c.startswith("_") and c.endswith("_key")]
    return out.drop(columns=drop_cols, errors="ignore")
