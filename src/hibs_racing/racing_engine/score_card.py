from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

from hibs_racing.config import load_config, ranker_model_path
from hibs_racing.features.ranker_matrix import impute_enrich_features, ranker_feature_columns
from hibs_racing.models.ranker_preflight import is_production_mode
from hibs_racing.ranker_features import resolve_ranker_feature_path


def _resolve_paths(
    model_path: str | Path | None,
    feature_json_path: str | Path | None,
    config_path: Path | None,
) -> tuple[Path, Path]:
    cfg = load_config(config_path)
    mp = Path(model_path) if model_path else ranker_model_path(cfg)
    fp = Path(feature_json_path) if feature_json_path else resolve_ranker_feature_path(cfg)
    return mp, fp


def _load_feature_cols(feature_json_path: Path) -> list[str]:
    payload = json.loads(feature_json_path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return payload
    return list(payload.get("features") or ranker_feature_columns())


def _impute_column(series: pd.Series, col: str) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    if "win_rate" in col or "flag" in col or col.endswith("_position"):
        return numeric.fillna(0.0)
    if col == "form_trip_change_f":
        return numeric.fillna(0.0)
    median = float(numeric.median()) if numeric.notna().any() else 0.0
    return numeric.fillna(median)


def _build_feature_matrix(race_df: pd.DataFrame, feature_cols: list[str]) -> pd.DataFrame:
    work = race_df
    try:
        from hibs_racing.cards.enrich import ENRICH_RANKER_FEATURES

        if any(col in work.columns for col in ENRICH_RANKER_FEATURES):
            work = impute_enrich_features(work.copy(), log_warnings=False)
    except Exception:
        work = race_df

    x = pd.DataFrame(index=work.index)
    for col in feature_cols:
        if col in work.columns:
            x[col] = _impute_column(work[col], col)
        else:
            x[col] = 0.0
    return x


def attach_win_probs(race_df: pd.DataFrame, *, score_col: str = "model_raw_score") -> pd.DataFrame:
    """Per-race softmax: raw ranker/heuristic scores → model_win_prob."""
    out = race_df.copy()
    scores = pd.to_numeric(out[score_col], errors="coerce").fillna(0.0)
    max_scores = scores.groupby(out["race_id"], sort=False).transform("max")
    exp_score = np.exp(scores - max_scores)
    sum_exp = exp_score.groupby(out["race_id"], sort=False).transform("sum")
    field_size = out.groupby("race_id", sort=False)[score_col].transform("count")
    out["exp_score"] = exp_score
    out["model_win_prob"] = np.where(sum_exp > 0, exp_score / sum_exp, 1.0 / field_size)
    out["model_score"] = scores
    return out


def run_legacy_heuristic(race_df: pd.DataFrame, reason: str = "") -> pd.DataFrame:
    """Backup scoring protocol utilizing the original weighted formula."""
    out = race_df.copy()
    out["model_raw_score"] = (
        out["combo_bayes_place"].fillna(0) * 2.0
        + out["sectional_composite"].fillna(0) * 1.5
        + out["hidden_potential"].fillna(0) * 0.02
        + out["finishing_burst_level"].fillna(0) * 0.25
        + out["or_vs_field"].fillna(0) * 0.01
        + out["combo_vs_field"].fillna(0) * 1.5
        + out.get("jockey_bayes_place", pd.Series(0, index=out.index)).fillna(0) * 0.75
        + out.get("trainer_bayes_place", pd.Series(0, index=out.index)).fillna(0) * 0.75
        + out.get("jockey_vs_field", pd.Series(0, index=out.index)).fillna(0) * 1.0
        + out.get("trainer_vs_field", pd.Series(0, index=out.index)).fillna(0) * 1.0
    )
    out["scoring_method"] = "heuristic"
    out["scoring_fallback_reason"] = reason or "Legacy heuristic"
    return attach_win_probs(out)


def apply_scoring_production_guard(
    *,
    model_path: Path,
    feature_path: Path,
    scoring_mode: str = "ranker",
) -> None:
    """
    Fail fast in production when ranker-only mode is configured but artifacts are absent.
    Prevents silent fallback to uncalibrated heuristic scores on live cards.
    """
    if scoring_mode != "ranker":
        return
    from hibs_racing.models.ranker_preflight import RankerPreflightError, verify_ranker_artifacts
    from hibs_racing.models.ranker_manifest import ranker_manifest_path

    try:
        verify_ranker_artifacts(
            model_path=model_path,
            feature_path=feature_path,
            manifest_path=ranker_manifest_path(),
            require_manifest=False,
        )
    except RankerPreflightError as exc:
        raise FileNotFoundError(str(exc)) from exc


def apply_scoring(
    race_df: pd.DataFrame,
    *,
    model_path: str | Path | None = None,
    feature_json_path: str | Path | None = None,
    config_path: Path | None = None,
) -> pd.DataFrame:
    """
    LightGBM LambdaRank inference on today's race field.
    Falls back safely to legacy heuristic if artifacts or dependencies are missing (auto mode).
    """
    cfg = load_config(config_path)
    mode = cfg.get("ranker", {}).get("scoring_mode", "auto")
    if is_production_mode():
        mode = cfg.get("ranker", {}).get("production_scoring_mode", "ranker")
    mp, fp = _resolve_paths(model_path, feature_json_path, config_path)

    apply_scoring_production_guard(model_path=mp, feature_path=fp, scoring_mode=mode)

    if mode == "heuristic":
        return run_legacy_heuristic(race_df, reason="scoring_mode=heuristic")

    if not os.path.exists(mp) or not os.path.exists(fp):
        if mode == "ranker":
            raise FileNotFoundError(
                f"ranker scoring_mode=ranker but artifacts missing: model={mp}, features={fp}"
            )
        return run_legacy_heuristic(race_df, reason="Model artifacts missing")

    try:
        import lightgbm as lgb

        feature_cols = _load_feature_cols(fp)
        if not feature_cols:
            raise ValueError("Feature JSON empty")

        x_live = _build_feature_matrix(race_df, feature_cols)
        bst = lgb.Booster(model_file=str(mp))
        model_features = bst.feature_name()
        if model_features and list(model_features) != feature_cols:
            feature_cols = list(model_features)
            x_live = _build_feature_matrix(race_df, feature_cols)

        out = race_df.copy()
        out["model_raw_score"] = bst.predict(x_live)
        out["scoring_method"] = "ranker"
        out["scoring_fallback_reason"] = ""
        return attach_win_probs(out)

    except ImportError as exc:
        if mode == "ranker":
            raise ImportError('Install ranker extras: pip install -e ".[ranker]"') from exc
        return run_legacy_heuristic(race_df, reason=f"Inference execution failure: {exc}")

    except (OSError, Exception) as exc:
        if mode == "ranker":
            raise RuntimeError(f"Ranker inference failed: {exc}") from exc
        return run_legacy_heuristic(race_df, reason=f"Inference execution failure: {exc}")
