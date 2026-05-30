from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from hibs_racing.config import load_config, ranker_feature_path, ranker_model_path
from hibs_racing.features.ranker_matrix import build_ranker_matrix, ranker_feature_columns


@dataclass
class RankerTrainReport:
    rows: int
    races: int
    ndcg_at_3: float | None
    top1_hit_rate: float | None
    previous_top1_hit_rate: float | None
    top1_delta: float | None
    model_path: str | None
    message: str

    def to_dict(self) -> dict:
        return {
            "rows": self.rows,
            "races": self.races,
            "ndcg_at_3": round(self.ndcg_at_3, 4) if self.ndcg_at_3 is not None else None,
            "top1_hit_rate": round(self.top1_hit_rate, 4) if self.top1_hit_rate is not None else None,
            "previous_top1_hit_rate": round(self.previous_top1_hit_rate, 4)
            if self.previous_top1_hit_rate is not None
            else None,
            "top1_delta": round(self.top1_delta, 4) if self.top1_delta is not None else None,
            "model_path": self.model_path,
            "message": self.message,
        }


def _holdout_top1_hit_rate(test: pd.DataFrame, features: list[str], *, ranker) -> float | None:
    from hibs_racing.racing_engine.score_card import _build_feature_matrix

    usable = [c for c in features if c in test.columns]
    if not usable:
        return None
    scored = test.copy()
    scored["pred_score"] = ranker.predict(_build_feature_matrix(scored, usable))
    scored["pred_rank"] = scored.groupby("race_id")["pred_score"].rank(ascending=False, method="first")
    top1 = scored[scored["pred_rank"] == 1]
    return float((top1["finish_pos"] == 1).mean()) if len(top1) else None


def _relevance_labels(finish_pos: pd.Series, race_id: pd.Series) -> pd.Series:
    """LambdaRank: higher label = better runner (winner highest, non-negative)."""
    pos = finish_pos.astype(float)
    max_pos = pos.groupby(race_id, sort=False).transform("max")
    return max_pos - pos + 1.0


def save_ranker_artifacts(
    ranker,
    features: list[str],
    *,
    model_path: Path | None = None,
    feature_path: Path | None = None,
) -> tuple[Path, Path]:
    mp = model_path or ranker_model_path()
    fp = feature_path or ranker_feature_path()
    mp.parent.mkdir(parents=True, exist_ok=True)
    ranker.booster_.save_model(str(mp))
    fp.write_text(json.dumps({"features": features}, indent=2), encoding="utf-8")
    return mp, fp


def load_ranker_features(path: Path | None = None) -> list[str]:
    fp = path or ranker_feature_path()
    if not fp.exists():
        return ranker_feature_columns()
    payload = json.loads(fp.read_text(encoding="utf-8"))
    return payload.get("features") or ranker_feature_columns()


def load_ranker(model_path: Path | None = None):
    """Return LightGBM Booster or None if missing / lightgbm not installed."""
    try:
        import lightgbm as lgb
    except (ImportError, OSError):
        return None
    mp = model_path or ranker_model_path()
    if not mp.exists():
        return None
    try:
        return lgb.Booster(model_file=str(mp))
    except OSError:
        return None


def predict_ranker_scores(
    frame: pd.DataFrame,
    *,
    ranker=None,
    features: list[str] | None = None,
) -> pd.Series | None:
    """Inference on a feature frame; returns None when no model is available."""
    ranker = ranker if ranker is not None else load_ranker()
    if ranker is None:
        return None
    features = features or load_ranker_features()
    if not features:
        return None
    from hibs_racing.racing_engine.score_card import _build_feature_matrix

    x = _build_feature_matrix(frame, features)
    scores = ranker.predict(x)
    return pd.Series(scores, index=frame.index)


def heuristic_model_score(frame: pd.DataFrame) -> pd.Series:
    """Legacy weighted sum — used by tests and training diagnostics."""
    from hibs_racing.racing_engine.score_card import run_legacy_heuristic

    scored = run_legacy_heuristic(frame, reason="direct heuristic call")
    return scored["model_raw_score"]


def train_lgbm_ranker(
    frame: pd.DataFrame | None = None,
    *,
    config_path: Path | None = None,
    min_rows: int | None = None,
    min_races: int | None = None,
    save: bool = True,
) -> RankerTrainReport:
    """
    Learning-to-rank with LightGBM (optional dependency).
    Evaluates on holdout split, then retrains on all rows and saves booster artifact.
    """
    try:
        import lightgbm as lgb
    except (ImportError, OSError) as exc:
        raise ImportError('Install ranker extras: pip install -e ".[ranker]"') from exc

    cfg = load_config(config_path)
    ranker_cfg = cfg.get("ranker", {})
    min_rows = min_rows if min_rows is not None else ranker_cfg.get("min_rows", 500)
    min_races = min_races if min_races is not None else ranker_cfg.get("min_races", 50)

    if frame is None:
        frame = build_ranker_matrix(export_parquet=False, config_path=config_path)

    if frame.empty:
        return RankerTrainReport(0, 0, None, None, None, None, None, "No rows — ingest + tag first.")

    features = [c for c in ranker_feature_columns() if c in frame.columns]
    df = frame.dropna(subset=["finish_pos"]).copy()
    df = df.sort_values(["race_date", "race_id"])

    if len(df) < min_rows or df["race_id"].nunique() < min_races:
        return RankerTrainReport(
            len(df),
            df["race_id"].nunique(),
            None,
            None,
            None,
            None,
            None,
            f"Need >={min_rows} rows and >={min_races} races (have {len(df)} / {df['race_id'].nunique()}).",
        )

    train_end = cfg["backtest"]["train_end"]
    test_start = cfg["backtest"]["test_start"]
    train = df[df["race_date"] <= train_end]
    test = df[df["race_date"] >= test_start]
    if train.empty or test.empty:
        return RankerTrainReport(
            len(df),
            df["race_id"].nunique(),
            None,
            None,
            None,
            None,
            None,
            "Adjust train_end / test_start in ingest/config.yaml.",
        )

    def _fit(sub: pd.DataFrame) -> lgb.LGBMRanker:
        x = sub[features]
        y = _relevance_labels(sub["finish_pos"], sub["race_id"])
        groups = sub.groupby("race_id", sort=False).size().to_numpy()
        model = lgb.LGBMRanker(
            objective="lambdarank",
            metric="ndcg",
            n_estimators=120,
            learning_rate=0.05,
            num_leaves=31,
            verbose=-1,
        )
        model.fit(x, y, group=groups)
        return model

    eval_model = _fit(train)
    test = test.copy()
    test["pred_score"] = eval_model.predict(test[features])
    test["pred_rank"] = test.groupby("race_id")["pred_score"].rank(ascending=False, method="first")
    top1 = test[test["pred_rank"] == 1]
    top1_hit = (top1["finish_pos"] == 1).mean() if len(top1) else 0.0

    previous_top1: float | None = None
    prior_booster = load_ranker(ranker_model_path(cfg))
    if prior_booster is not None:
        try:
            previous_top1 = _holdout_top1_hit_rate(
                test,
                list(prior_booster.feature_name()),
                ranker=prior_booster,
            )
        except Exception:
            previous_top1 = None
    top1_delta = float(top1_hit - previous_top1) if previous_top1 is not None else None

    model_path_str: str | None = None
    if save:
        final = _fit(df)
        mp, _ = save_ranker_artifacts(
            final,
            features,
            model_path=ranker_model_path(cfg),
            feature_path=ranker_feature_path(cfg),
        )
        model_path_str = str(mp)
        try:
            from hibs_racing.models.feature_impact import export_feature_impact_artifacts

            export_feature_impact_artifacts(final.booster_, df[features], features, config_path=config_path)
        except Exception:
            pass  # training succeeds even if chart export fails

    msg = "Ranker trained and saved — score-card uses model when artifact exists."
    if previous_top1 is not None and top1_delta is not None:
        sign = "+" if top1_delta >= 0 else ""
        msg = (
            f"Holdout top-1: {top1_hit:.1%} vs prior model {previous_top1:.1%} "
            f"({sign}{top1_delta:.1%}). Model saved."
        )

    return RankerTrainReport(
        rows=len(df),
        races=df["race_id"].nunique(),
        ndcg_at_3=None,
        top1_hit_rate=float(top1_hit),
        previous_top1_hit_rate=previous_top1,
        top1_delta=top1_delta,
        model_path=model_path_str,
        message=msg,
    )
