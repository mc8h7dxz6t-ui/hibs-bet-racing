from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from hibs_racing.cards.enrich import ENRICH_RANKER_FEATURES, compute_enrich_ranker_fields
from hibs_racing.config import db_path, load_config
from hibs_racing.features.cd_stats import add_all_cd_stats
from hibs_racing.features.combo_stats import add_point_in_time_combo_stats
from hibs_racing.features.discrepancy import add_discrepancy_features
from hibs_racing.features.entity_stats import add_all_entity_stats
from hibs_racing.features.store import connect, init_db
from hibs_racing.nlp.pipeline import parse_comment
from hibs_racing.odds.matching import normalize_horse_name

logger = logging.getLogger(__name__)

EXPECTED_BASE_FEATURE_COUNT = 36
EXPECTED_ENRICH_FEATURE_COUNT = 48

RUNNER_ENRICH_QUERY_COLUMNS: tuple[str, ...] = (
    "form_string",
    "trainer_14d_wins",
    "trainer_14d_runs",
    "horse_course_win_rate",
    "horse_distance_win_rate",
    "horse_going_win_rate",
    "jockey_rp_14d_win_rate",
    "trainer_rp_14d_win_rate",
    "trainer_rtf",
    "trainer_14d_strike",
    "form_lto_position",
    "form_trip_change_f",
    "form_cd_flag",
    "form_bf_flag",
    "form_poor_runs_3",
)


class RankerMatrixValidationError(ValueError):
    """Raised when ranker matrix fails structural integrity checks."""


RANKER_QUERY_BASE = """
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


def _runner_select_sql(db: Path, *, with_enrich: bool) -> str:
    init_db(db)
    with connect(db) as conn:
        existing = {row[1] for row in conn.execute("PRAGMA table_info(runners)").fetchall()}
    enrich_cols = [c for c in RUNNER_ENRICH_QUERY_COLUMNS if c in existing] if with_enrich else []
    enrich_sql = ""
    if enrich_cols:
        enrich_sql = ",\n    " + ",\n    ".join(f"r.{col}" for col in enrich_cols)
    return RANKER_QUERY_BASE.replace(
        "COALESCE(t.late_pace_level, 0) AS late_pace_level",
        f"COALESCE(t.late_pace_level, 0) AS late_pace_level{enrich_sql}",
    )


def load_runner_frame(database: Path | None = None, *, with_enrich: bool = False) -> pd.DataFrame:
    cfg = load_config()
    db = database or db_path(cfg)
    init_db(db)
    query = _runner_select_sql(db, with_enrich=with_enrich)
    with connect(db) as conn:
        return pd.read_sql_query(query, conn)


def enrich_feature_coverage(frame: pd.DataFrame) -> dict[str, float]:
    if frame.empty:
        return {col: 0.0 for col in ENRICH_RANKER_FEATURES}
    out: dict[str, float] = {}
    n = len(frame)
    for col in ENRICH_RANKER_FEATURES:
        if col not in frame.columns:
            out[col] = 0.0
            continue
        filled = int(frame[col].notna().sum())
        out[col] = round(100.0 * filled / n, 2)
    return out


def impute_enrich_features(frame: pd.DataFrame, *, log_warnings: bool = True) -> pd.DataFrame:
    """Training-safe imputation for sparse historical enrich coverage."""
    out = compute_enrich_ranker_fields(frame)
    for col in ENRICH_RANKER_FEATURES:
        if col not in out.columns:
            out[col] = 0.0 if "flag" in col or "win_rate" in col else np.nan
        series = pd.to_numeric(out[col], errors="coerce")
        null_count = int(series.isna().sum())
        if null_count and log_warnings:
            coverage = 100.0 * (len(out) - null_count) / len(out)
            logger.warning(
                "Enrich feature '%s' missing %s rows (coverage %.2f%%)",
                col,
                null_count,
                coverage,
            )
        if "win_rate" in col or "flag" in col or col.endswith("_position"):
            out[col] = series.fillna(0.0)
        elif col == "form_trip_change_f":
            out[col] = series.fillna(0.0)
        else:
            median = float(series.median()) if series.notna().any() else 0.0
            out[col] = series.fillna(median)
    return out


def validate_ranker_matrix(
    frame: pd.DataFrame,
    *,
    with_enrich: bool,
    feature_cols: list[str],
    min_enrich_coverage_pct: float = 0.0,
) -> dict[str, float]:
    """Crash safely instead of silently down-training."""
    if frame.empty:
        raise RankerMatrixValidationError("Ranker matrix is empty — ingest + tag first.")

    present = [c for c in feature_cols if c in frame.columns]
    expected = EXPECTED_ENRICH_FEATURE_COUNT if with_enrich else EXPECTED_BASE_FEATURE_COUNT
    if len(present) != expected:
        missing = [c for c in feature_cols if c not in frame.columns]
        raise RankerMatrixValidationError(
            f"Feature count mismatch: expected {expected}, compiled {len(present)}. "
            f"Missing: {missing}. Run migrations + backfill-runner-enrich before --with-enrich."
        )

    coverage = enrich_feature_coverage(frame) if with_enrich else {}
    if with_enrich:
        missing_schema = [c for c in ENRICH_RANKER_FEATURES if c not in frame.columns]
        if missing_schema:
            raise RankerMatrixValidationError(
                f"Missing enrich schema columns in matrix: {missing_schema}"
            )
        mean_cov = sum(coverage.values()) / len(coverage) if coverage else 0.0
        if min_enrich_coverage_pct > 0 and mean_cov < min_enrich_coverage_pct:
            raise RankerMatrixValidationError(
                f"Enrich coverage {mean_cov:.2f}% below minimum {min_enrich_coverage_pct:.2f}%. "
                "Run backfill-runner-enrich and scrape historical RP racecards before training."
            )
    return coverage


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
    with_enrich: bool = False,
) -> pd.DataFrame:
    """
    Unified LTR feature matrix: one row per runner, grouped by race_id.
    Combo stats are point-in-time; NLP and OR features are race-relative.
    """
    cfg = load_config(config_path)
    db = database or db_path(cfg)
    alpha = cfg.get("ranker", {}).get("combo_alpha", 8.0)
    place_cutoff = cfg["backtest"].get("place_cutoff_default", 3)

    logger.info(
        "Compiling ranker matrix mode=%s",
        "enrich_48" if with_enrich else "base_36",
    )

    frame = load_runner_frame(db, with_enrich=with_enrich)
    if frame.empty:
        return frame

    frame = add_point_in_time_combo_stats(frame, alpha=alpha, place_cutoff=place_cutoff)
    frame = add_all_entity_stats(frame, alpha=alpha, place_cutoff=place_cutoff)
    frame = add_all_cd_stats(frame, alpha=alpha, place_cutoff=place_cutoff)
    frame = add_discrepancy_features(frame)
    frame = add_within_race_features(frame)

    if with_enrich:
        raw_coverage = enrich_feature_coverage(frame)
        mean_raw = sum(raw_coverage.values()) / len(raw_coverage) if raw_coverage else 0.0
        min_cov = float(cfg.get("ranker", {}).get("min_enrich_coverage_pct", 0.0))
        if min_cov > 0 and mean_raw < min_cov:
            raise RankerMatrixValidationError(
                f"Raw enrich coverage {mean_raw:.2f}% below minimum {min_cov:.2f}%. "
                "Run backfill-runner-enrich and scrape historical RP racecards before training."
            )
        frame = impute_enrich_features(frame)
        
        # Institutional++ Explicit 48-Feature Alignment Guard
        manifest_48 = [
            "official_rating", "rpr", "combo_bayes_win", "combo_bayes_place", "combo_prior_rides",
            "jockey_bayes_place", "trainer_bayes_place", "jockey_place_90d", "trainer_place_90d",
            "jockey_place_14d", "trainer_place_14d", "jockey_consistency", "trainer_consistency",
            "jockey_vs_field", "trainer_vs_field", "jockey_cd_bayes_place", "trainer_cd_bayes_place",
            "combo_cd_bayes_place", "combo_cd_prior_rides", "jockey_cdd_bayes_place", "trainer_cdd_bayes_place",
            "combo_cdd_bayes_place", "jockey_cd_vs_field", "trainer_cd_vs_field", "combo_cd_vs_field",
            "combo_cdd_vs_field", "hidden_potential", "or_vs_field", "rpr_vs_field", "nlp_pace_vs_field",
            "nlp_pace_rank", "combo_vs_field", "draw_bias_z", "sectional_composite", "finishing_burst_level",
            "days_since_last_run", "horse_course_win_rate", "horse_distance_win_rate", "horse_going_win_rate",
            "jockey_rp_14d_win_rate", "trainer_rp_14d_win_rate", "trainer_rtf", "trainer_14d_strike",
            "form_lto_position", "form_trip_change_f", "form_cd_flag", "form_bf_flag", "form_poor_runs_3"
        ]
        for col in manifest_48:
            if col not in frame.columns:
                frame[col] = float("nan")
        
        # Enforce exact column positioning order
        base_cols = [c for c in frame.columns if c not in manifest_48]
        frame = frame[base_cols + manifest_48]
        frame.attrs["enrich_coverage_raw_pct"] = raw_coverage

    feature_cols = ranker_enrich_feature_columns() if with_enrich else ranker_feature_columns()
    validate_ranker_matrix(
        frame,
        with_enrich=with_enrich,
        feature_cols=feature_cols,
        min_enrich_coverage_pct=0.0,
    )

    frame["won"] = (frame["finish_pos"] == 1).astype(int)
    frame["placed"] = (frame["finish_pos"] <= place_cutoff).astype(int)
    frame["hidden_potential"] = frame["hidden_potential"].fillna(0.0)

    built_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    _persist_ranker_features(db, frame, built_at)

    if export_parquet:
        out_path = Path(cfg["paths"]["parquet_dir"]) / (
            "ranker_matrix_enrich.parquet" if with_enrich else "ranker_matrix.parquet"
        )
        out_path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(out_path, index=False)

    return frame


def _persist_ranker_features(db: Path, frame: pd.DataFrame, built_at: str) -> int:
    init_db(db)
    cols = [
        "runner_id", "race_id", "combo_prior_rides", "combo_bayes_win",
        "combo_bayes_place", "hidden_potential", "or_vs_field", "rpr_vs_field",
        "nlp_pace_vs_field", "nlp_pace_rank", "combo_vs_field", "draw_bias_z",
        "finish_pos", "won", "placed",
        "horse_course_win_rate", "horse_distance_win_rate", "horse_going_win_rate",
        "jockey_rp_14d_win_rate", "trainer_rp_14d_win_rate", "trainer_rtf",
        "trainer_14d_strike", "form_lto_position", "form_trip_change_f",
        "form_cd_flag", "form_bf_flag", "form_poor_runs_3"
    ]
    with connect(db) as conn:
        for col in cols[15:]:
            try: conn.execute(f"ALTER TABLE ranker_features ADD COLUMN {col} REAL;")
            except Exception: pass
    count = 0
    with connect(db) as conn:
        conn.execute("DELETE FROM ranker_features")
        placeholders = ", ".join(["?"] * (len(cols) + 1))
        columns_str = ", ".join(cols) + ", built_at"
        sql_query = f"INSERT INTO ranker_features ({columns_str}) VALUES ({placeholders})"
        for rec in frame.to_dict(orient="records"):
            exec_tuple = (
                rec["runner_id"], rec["race_id"], int(rec.get("combo_prior_rides") or 0),
                rec.get("combo_bayes_win"), rec.get("combo_bayes_place"), rec.get("hidden_potential") or 0,
                rec.get("or_vs_field"), rec.get("rpr_vs_field"), rec.get("nlp_pace_vs_field"),
                rec.get("nlp_pace_rank"), rec.get("combo_vs_field"), rec.get("draw_bias_z"),
                int(rec["finish_pos"]) if pd.notna(rec.get("finish_pos")) else None,
                int(rec.get("won") or 0), int(rec.get("placed") or 0),
                rec.get("horse_course_win_rate", float("nan")), rec.get("horse_distance_win_rate", float("nan")),
                rec.get("horse_going_win_rate", float("nan")), rec.get("jockey_rp_14d_win_rate", float("nan")),
                rec.get("trainer_rp_14d_win_rate", float("nan")), rec.get("trainer_rtf", float("nan")),
                rec.get("trainer_14d_strike", float("nan")), rec.get("form_lto_position", float("nan")),
                rec.get("form_trip_change_f", float("nan")), rec.get("form_cd_flag", float("nan")),
                rec.get("form_bf_flag", float("nan")), rec.get("form_poor_runs_3", float("nan")),
                built_at
            )
            conn.execute(sql_query, exec_tuple)
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


def ranker_enrich_feature_columns() -> list[str]:
    # Institutional++ Invariant 48-Feature Manifest Specification
    return [
        "official_rating", "rpr", "combo_bayes_win", "combo_bayes_place", "combo_prior_rides",
        "jockey_bayes_place", "trainer_bayes_place", "jockey_place_90d", "trainer_place_90d",
        "jockey_place_14d", "trainer_place_14d", "jockey_consistency", "trainer_consistency",
        "jockey_vs_field", "trainer_vs_field", "jockey_cd_bayes_place", "trainer_cd_bayes_place",
        "combo_cd_bayes_place", "combo_cd_prior_rides", "jockey_cdd_bayes_place", "trainer_cdd_bayes_place",
        "combo_cdd_bayes_place", "jockey_cd_vs_field", "trainer_cd_vs_field", "combo_cd_vs_field",
        "combo_cdd_vs_field", "hidden_potential", "or_vs_field", "rpr_vs_field", "nlp_pace_vs_field",
        "nlp_pace_rank", "combo_vs_field", "draw_bias_z", "sectional_composite", "finishing_burst_level",
        "days_since_last_run", "horse_course_win_rate", "horse_distance_win_rate", "horse_going_win_rate",
        "jockey_rp_14d_win_rate", "trainer_rp_14d_win_rate", "trainer_rtf", "trainer_14d_strike",
        "form_lto_position", "form_trip_change_f", "form_cd_flag", "form_bf_flag", "form_poor_runs_3"
    ]

def _nlp_history_index(hist: pd.DataFrame) -> pd.DataFrame:
    """Point-in-time NLP keyed by normalized horse name (bridges API horse_id vs name history)."""
    if hist.empty:
        return pd.DataFrame(columns=["_hn", "sectional_composite", "finishing_burst_level", "late_pace_level"])
    slug = hist.copy()
    slug["_hn"] = slug["horse_id"].astype(str).map(normalize_horse_name)
    slug = slug[slug["_hn"].astype(str).str.len() > 0]
    return (
        slug.sort_values("race_date", ascending=False)
        .drop_duplicates(subset=["_hn"], keep="first")
        .set_index("_hn")[["sectional_composite", "finishing_burst_level", "late_pace_level"]]
    )


def _attach_card_nlp(cards: pd.DataFrame, hist: pd.DataFrame) -> pd.DataFrame:
    """Latest historical NLP per horse; parse card_comment when no history."""
    out = cards.copy()
    nlp_cols = ["sectional_composite", "finishing_burst_level", "late_pace_level"]
    if hist.empty:
        for col in nlp_cols:
            out[col] = 0.0 if col == "sectional_composite" else 0
    else:
        nlp = _nlp_history_index(hist)
        name_col = "horse_name" if "horse_name" in out.columns else "horse_id"
        out["_hn"] = out[name_col].astype(str).map(normalize_horse_name)
        for col in nlp_cols:
            by_name = out["_hn"].map(nlp[col]) if not nlp.empty else pd.Series(index=out.index, dtype=float)
            by_id = out["horse_id"].map(
                hist.sort_values("race_date", ascending=False)
                .drop_duplicates(subset=["horse_id"], keep="first")
                .set_index("horse_id")[col]
            )
            out[col] = by_name.combine_first(by_id)
        out = out.drop(columns=["_hn"], errors="ignore")
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
    upcoming = compute_enrich_ranker_fields(upcoming)
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
    combined = compute_enrich_ranker_fields(combined)
    combined["hidden_potential"] = combined["hidden_potential"].fillna(0.0)

    card_ids = set(upcoming["runner_id"])
    out = combined[combined["runner_id"].isin(card_ids)].copy()
    return out.drop(columns=["_is_card"], errors="ignore")
