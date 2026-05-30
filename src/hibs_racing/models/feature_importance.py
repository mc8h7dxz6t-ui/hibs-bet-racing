from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from hibs_racing.config import load_config, ranker_feature_path, ranker_model_path
from hibs_racing.features.ranker_matrix import build_ranker_matrix, ranker_feature_columns
from hibs_racing.models.lgbm_ranker import load_ranker, load_ranker_features


@dataclass
class FeatureImportanceRow:
    feature: str
    gain: float
    split: float
    gain_pct: float
    split_pct: float
    rank: int

    def to_dict(self) -> dict:
        return {
            "rank": self.rank,
            "feature": self.feature,
            "gain": round(self.gain, 6),
            "split": round(self.split, 2),
            "gain_pct": round(self.gain_pct, 2),
            "split_pct": round(self.split_pct, 2),
        }


def _importance_types() -> list[str]:
    return ["gain", "split"]


def _extract_importance(booster, features: list[str]) -> tuple[list[float], list[float]]:
    gain = booster.feature_importance(importance_type="gain")
    split = booster.feature_importance(importance_type="split")
    if len(gain) != len(features):
        # LightGBM may omit unused features — align by index when counts match canonical list
        pass
    return list(gain), list(split)


def build_feature_importance_matrix(
    *,
    model_path: Path | None = None,
    feature_path: Path | None = None,
    config_path: Path | None = None,
) -> list[FeatureImportanceRow]:
    """Ranked feature importance from saved LightGBM booster."""
    booster = load_ranker(model_path or ranker_model_path(load_config(config_path)))
    if booster is None:
        raise FileNotFoundError(
            "LightGBM model not found. Run: hibs-racing build-matrix && hibs-racing train-ranker"
        )

    features = load_ranker_features(feature_path or ranker_feature_path(load_config(config_path)))
    gain, split = _extract_importance(booster, features)
    gain_total = sum(gain) or 1.0
    split_total = sum(split) or 1.0

    rows: list[FeatureImportanceRow] = []
    for idx, name in enumerate(features):
        g = float(gain[idx]) if idx < len(gain) else 0.0
        s = float(split[idx]) if idx < len(split) else 0.0
        rows.append(
            FeatureImportanceRow(
                feature=name,
                gain=g,
                split=s,
                gain_pct=100.0 * g / gain_total,
                split_pct=100.0 * s / split_total,
                rank=0,
            )
        )
    rows.sort(key=lambda r: r.gain, reverse=True)
    for i, row in enumerate(rows, start=1):
        row.rank = i
    return rows


def _holdout_metrics(config_path: Path | None = None) -> dict:
    """Winner / place AUC on configured holdout split — explains ranker signal strength."""
    try:
        from sklearn.metrics import roc_auc_score
    except ImportError:
        return {"message": "Install scikit-learn for holdout AUC"}

    cfg = load_config(config_path)
    train_end = cfg["backtest"]["train_end"]
    test_start = cfg["backtest"]["test_start"]
    frame = build_ranker_matrix(export_parquet=False, config_path=config_path)
    if frame.empty:
        return {"message": "No ranker matrix rows"}

    features = [c for c in ranker_feature_columns() if c in frame.columns]
    test = frame[(frame["race_date"] >= test_start) & frame["finish_pos"].notna()].copy()
    if test.empty:
        return {"message": "Empty holdout split — adjust train_end / test_start"}

    booster = load_ranker(ranker_model_path(cfg))
    if booster is None:
        return {"message": "Model missing"}

    x = test[features].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    scores = booster.predict(x)
    test = test.assign(pred_score=scores)

    winner_auc = roc_auc_score((test["finish_pos"] == 1).astype(int), test["pred_score"])
    place_cut = int(cfg["backtest"].get("place_cutoff_default", 3))
    place_auc = roc_auc_score((test["finish_pos"] <= place_cut).astype(int), test["pred_score"])

    top1 = test.loc[test.groupby("race_id")["pred_score"].idxmax()]
    top1_hit = float((top1["finish_pos"] == 1).mean())

    return {
        "holdout_rows": len(test),
        "holdout_races": int(test["race_id"].nunique()),
        "train_end": train_end,
        "test_start": test_start,
        "winner_auc": round(float(winner_auc), 4),
        "place_auc": round(float(place_auc), 4),
        "top1_hit_rate": round(top1_hit, 4),
    }


def format_importance_table(rows: list[FeatureImportanceRow]) -> str:
    """ASCII matrix for terminal output."""
    headers = ("Rank", "Feature", "Gain", "Gain %", "Split", "Split %")
    col_widths = [4, 22, 10, 8, 8, 8]
    lines = [
        "Feature Importance Matrix (LightGBM LambdaRank)",
        "=" * 72,
        " ".join(h.ljust(w) for h, w in zip(headers, col_widths, strict=True)),
        "-" * 72,
    ]
    for row in rows:
        lines.append(
            f"{row.rank:<4} {row.feature:<22} {row.gain:>10.2f} {row.gain_pct:>7.1f}% "
            f"{row.split:>8.0f} {row.split_pct:>7.1f}%"
        )
    lines.append("=" * 72)
    return "\n".join(lines)


def feature_importance_report(
    *,
    config_path: Path | None = None,
    include_holdout: bool = True,
) -> dict:
    rows = build_feature_importance_matrix(config_path=config_path)
    report: dict = {
        "model_path": str(ranker_model_path(load_config(config_path))),
        "feature_count": len(rows),
        "importance_types": _importance_types(),
        "matrix": [r.to_dict() for r in rows],
        "top_drivers": [r.feature for r in rows[:5]],
    }
    if include_holdout:
        report["holdout"] = _holdout_metrics(config_path)
    return report


def print_feature_importance_report(*, config_path: Path | None = None, as_json: bool = False) -> dict:
    report = feature_importance_report(config_path=config_path)
    if as_json:
        print(json.dumps(report, indent=2))
    else:
        table_rows = [
            FeatureImportanceRow(
                feature=r["feature"],
                gain=r["gain"],
                split=r["split"],
                gain_pct=r["gain_pct"],
                split_pct=r["split_pct"],
                rank=r["rank"],
            )
            for r in report["matrix"]
        ]
        print(format_importance_table(table_rows))
        holdout = report.get("holdout") or {}
        if holdout.get("winner_auc") is not None:
            print(
                f"\nHoldout metrics ({holdout.get('test_start')} →): "
                f"winner AUC {holdout['winner_auc']:.3f}, "
                f"place AUC {holdout['place_auc']:.3f}, "
                f"top-1 hit {holdout['top1_hit_rate']:.1%}"
            )
        elif holdout.get("message"):
            print(f"\nHoldout: {holdout['message']}")
        print(f"\nTop drivers: {', '.join(report['top_drivers'])}")
    return report
