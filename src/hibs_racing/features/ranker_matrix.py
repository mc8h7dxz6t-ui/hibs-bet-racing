from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from hibs_racing.config import db_path, load_config
from hibs_racing.features.cd_stats import add_all_cd_stats
from hibs_racing.features.combo_stats import add_point_in_time_combo_stats
from hibs_racing.features.discrepancy import add_discrepancy_features
from hibs_racing.features.entity_stats import add_all_entity_stats
from hibs_racing.features.store import connect, init_db
from hibs_racing.nlp.pipeline import parse_comment

RANKER_QUERY = """
SELECT
    r.runner_id,
    r.race_id,
    r.race_date,
    r.horse_id,
    r.jockey,
    r.trainer,
    r.course,
    r.distance_f,
    r.draw,
    r.official_rating,
    r.rpr,
    r.race_class,
    r.days_since_last_run,
    r.finish_pos,
    r.field_size,
    COALESCE(t.sectional_composite, 0) AS sectional_composite,
    COALESCE(t.finishing_burst_level, 0) AS finishing_burst_level,
    COALESCE(t.late_pace_level, 0) AS late_pace_level
FROM runners r
LEFT JOIN comment_tags t ON t.runner_id = r.runner_id
WHERE r.finish_pos IS NOT NULL
"""


def load_runner_frame(database: Path | None = None) -> pd.DataFrame:
    cfg = load_config()
    db = database or db_path(cfg)
    init_db(db)
    with connect(db) as conn:
        return pd.read_sql_query(RANKER_QUERY, conn)


def add_within_race_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Relative features — each metric evaluated vs other runners in the same race."""
    out = frame.copy()
    by_race = out.groupby("race_id", sort=False)

    out["or_vs_field"] = out["official_rating"] - by_race["official_rating"].transform("mean")
    out["rpr_vs_field"] = out["rpr"] - by_race["rpr"].transform("mean")
    out["nlp_pace_vs_field"] = out["sectional_composite"] - by_race["sectional_composite"].transform("mean")
    out["nlp_pace_rank"] = by_race["sectional_composite"].rank(ascending=False, method="average")
    out["combo_vs_field"] = out["combo_bayes_win"] - by_race["combo_bayes_win"].transform("median")
    if "jockey_bayes_place" in out.columns:
        out["jockey_vs_field"] = out["jockey_bayes_place"] - by_race["jockey_bayes_place"].transform("median")
    else:
        out["jockey_vs_field"] = 0.0
    if "trainer_bayes_place" in out.columns:
        out["trainer_vs_field"] = out["trainer_bayes_place"] - by_race["trainer_bayes_place"].transform("median")
    else:
        out["trainer_vs_field"] = 0.0

    cd_vs_specs = (
        ("jockey_cd_bayes_place", "jockey_cd_vs_field"),
        ("trainer_cd_bayes_place", "trainer_cd_vs_field"),
        ("combo_cd_bayes_place", "combo_cd_vs_field"),
        ("combo_cdd_bayes_place", "combo_cdd_vs_field"),
    )
    for src, dst in cd_vs_specs:
        if src in out.columns:
            out[dst] = out[src] - by_race[src].transform("median")
        else:
            out[dst] = 0.0

    if "draw" in out.columns:
        draw_mean = by_race["draw"].transform("mean")
        draw_std = by_race["draw"].transform("std").replace(0, 1)
        out["draw_bias_z"] = (out["draw"] - draw_mean) / draw_std
    else:
        out["draw_bias_z"] = 0.0
    return out


def build_ranker_matrix(
    database: Path | None = None,
    *,
    config_path: Path | None = None,
    export_parquet: bool = True,
) -> pd.DataFrame:
    """
    Unified LTR feature matrix: one row per runner, grouped by race_id.
    Combo stats are point-in-time; NLP and OR features are race-relative.
    """
    cfg = load_config(config_path)
    db = database or db_path(cfg)
    alpha = cfg.get("ranker", {}).get("combo_alpha", 8.0)
    place_cutoff = cfg["backtest"].get("place_cutoff_default", 3)

    frame = load_runner_frame(db)
    if frame.empty:
        return frame

    frame = add_point_in_time_combo_stats(frame, alpha=alpha, place_cutoff=place_cutoff)
    frame = add_all_entity_stats(frame, alpha=alpha, place_cutoff=place_cutoff)
    frame = add_all_cd_stats(frame, alpha=alpha, place_cutoff=place_cutoff)
    frame = add_discrepancy_features(frame)
    frame = add_within_race_features(frame)

    frame["won"] = (frame["finish_pos"] == 1).astype(int)
    frame["placed"] = (frame["finish_pos"] <= place_cutoff).astype(int)
    frame["hidden_potential"] = frame["hidden_potential"].fillna(0.0)

    built_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    _persist_ranker_features(db, frame, built_at)

    if export_parquet:
        out_path = Path(cfg["paths"]["parquet_dir"]) / "ranker_matrix.parquet"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(out_path, index=False)

    return frame


def _persist_ranker_features(db: Path, frame: pd.DataFrame, built_at: str) -> int:
    init_db(db)
    cols = [
        "runner_id",
        "race_id",
        "combo_prior_rides",
        "combo_bayes_win",
        "combo_bayes_place",
        "hidden_potential",
        "or_vs_field",
        "rpr_vs_field",
        "nlp_pace_vs_field",
        "nlp_pace_rank",
        "combo_vs_field",
        "draw_bias_z",
        "finish_pos",
        "won",
        "placed",
    ]
    count = 0
    with connect(db) as conn:
        conn.execute("DELETE FROM ranker_features")
        for rec in frame[cols].to_dict(orient="records"):
            conn.execute(
                """
                INSERT INTO ranker_features (
                    runner_id, race_id, combo_prior_rides, combo_bayes_win,
                    combo_bayes_place, hidden_potential, or_vs_field, rpr_vs_field,
                    nlp_pace_vs_field, nlp_pace_rank, combo_vs_field, draw_bias_z,
                    finish_pos, won, placed, built_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rec["runner_id"],
                    rec["race_id"],
                    int(rec.get("combo_prior_rides") or 0),
                    rec.get("combo_bayes_win"),
                    rec.get("combo_bayes_place"),
                    rec.get("hidden_potential") or 0,
                    rec.get("or_vs_field"),
                    rec.get("rpr_vs_field"),
                    rec.get("nlp_pace_vs_field"),
                    rec.get("nlp_pace_rank"),
                    rec.get("combo_vs_field"),
                    rec.get("draw_bias_z"),
                    int(rec["finish_pos"]) if pd.notna(rec.get("finish_pos")) else None,
                    int(rec.get("won") or 0),
                    int(rec.get("placed") or 0),
                    built_at,
                ),
            )
            count += 1
        conn.commit()
    return count


def ranker_feature_columns() -> list[str]:
    return [
        "official_rating",
        "rpr",
        "combo_bayes_win",
        "combo_bayes_place",
        "combo_prior_rides",
        "jockey_bayes_place",
        "trainer_bayes_place",
        "jockey_place_90d",
        "trainer_place_90d",
        "jockey_place_14d",
        "trainer_place_14d",
        "jockey_consistency",
        "trainer_consistency",
        "jockey_vs_field",
        "trainer_vs_field",
        "jockey_cd_bayes_place",
        "trainer_cd_bayes_place",
        "combo_cd_bayes_place",
        "combo_cd_prior_rides",
        "jockey_cdd_bayes_place",
        "trainer_cdd_bayes_place",
        "combo_cdd_bayes_place",
        "jockey_cd_vs_field",
        "trainer_cd_vs_field",
        "combo_cd_vs_field",
        "combo_cdd_vs_field",
        "hidden_potential",
        "or_vs_field",
        "rpr_vs_field",
        "nlp_pace_vs_field",
        "nlp_pace_rank",
        "combo_vs_field",
        "draw_bias_z",
        "sectional_composite",
        "finishing_burst_level",
        "days_since_last_run",
    ]


def _attach_card_nlp(cards: pd.DataFrame, hist: pd.DataFrame) -> pd.DataFrame:
    """Latest historical NLP per horse; parse card_comment when no history."""
    out = cards.copy()
    if hist.empty:
        out["sectional_composite"] = 0.0
        out["finishing_burst_level"] = 0
        out["late_pace_level"] = 0
    else:
        nlp = (
            hist.sort_values("race_date", ascending=False)
            .drop_duplicates(subset=["horse_id"], keep="first")
            .set_index("horse_id")[["sectional_composite", "finishing_burst_level", "late_pace_level"]]
        )
        for col in nlp.columns:
            out[col] = out["horse_id"].map(nlp[col])
    out["sectional_composite"] = pd.to_numeric(out.get("sectional_composite"), errors="coerce").fillna(0.0)
    out["finishing_burst_level"] = pd.to_numeric(out.get("finishing_burst_level"), errors="coerce").fillna(0).astype(int)
    out["late_pace_level"] = pd.to_numeric(out.get("late_pace_level"), errors="coerce").fillna(0).astype(int)

    if "card_comment" in out.columns:
        missing = out["sectional_composite"] == 0
        for idx in out.index[missing]:
            text = out.at[idx, "card_comment"]
            if text:
                tags = parse_comment(str(text))
                out.at[idx, "sectional_composite"] = tags.sectional_composite
                out.at[idx, "finishing_burst_level"] = tags.finishing_burst_level
                out.at[idx, "late_pace_level"] = tags.late_pace_level
    return out


def build_card_feature_frame(
    cards: pd.DataFrame,
    database: Path | None = None,
    *,
    config_path: Path | None = None,
    hist_frame: pd.DataFrame | None = None,
    hist_before_date: str | None = None,
) -> pd.DataFrame:
    """
    Ranker-aligned features for upcoming card rows — same pipeline as build_ranker_matrix
    (point-in-time combo, expanding class history, within-race relatives).
    """
    cfg = load_config(config_path)
    db = database or db_path(cfg)
    alpha = cfg.get("ranker", {}).get("combo_alpha", 8.0)
    place_cutoff = cfg["backtest"].get("place_cutoff_default", 3)

    hist = hist_frame.copy() if hist_frame is not None else load_runner_frame(db)
    if hist_before_date:
        hist = hist[hist["race_date"] < hist_before_date]
    upcoming = cards.copy()
    upcoming["race_date"] = upcoming.get("card_date", upcoming.get("race_date"))
    for col in ("draw", "days_since_last_run", "field_size", "course", "distance_f"):
        if col not in upcoming.columns:
            upcoming[col] = np.nan
    upcoming = _attach_card_nlp(upcoming, hist)
    upcoming["finish_pos"] = np.nan
    upcoming["_is_card"] = 1
    if not hist.empty:
        hist = hist.copy()
        hist["_is_card"] = 0
        combined = pd.concat([hist, upcoming], ignore_index=True)
    else:
        combined = upcoming

    combined = combined.sort_values(["race_date", "_is_card", "race_id", "runner_id"]).reset_index(drop=True)
    combined["official_rating"] = pd.to_numeric(combined.get("official_rating"), errors="coerce")
    combined["rpr"] = pd.to_numeric(combined.get("rpr"), errors="coerce")
    combined["days_since_last_run"] = pd.to_numeric(combined.get("days_since_last_run"), errors="coerce")

    combined = add_point_in_time_combo_stats(combined, alpha=alpha, place_cutoff=place_cutoff)
    combined = add_all_entity_stats(combined, alpha=alpha, place_cutoff=place_cutoff)
    combined = add_all_cd_stats(combined, alpha=alpha, place_cutoff=place_cutoff)
    combined = add_discrepancy_features(combined)
    combined = add_within_race_features(combined)
    combined["hidden_potential"] = combined["hidden_potential"].fillna(0.0)

    card_ids = set(upcoming["runner_id"])
    out = combined[combined["runner_id"].isin(card_ids)].copy()
    return out.drop(columns=["_is_card"], errors="ignore")
