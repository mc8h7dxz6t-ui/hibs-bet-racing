from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from hibs_racing.config import load_config, model_dir, ranker_feature_path, ranker_model_path
from hibs_racing.features.ranker_matrix import ranker_feature_columns
from hibs_racing.models.feature_importance import (
    FeatureImportanceRow,
    _holdout_metrics,
    build_feature_importance_matrix,
)
from hibs_racing.models.lgbm_ranker import load_ranker, load_ranker_features

IMPACT_JSON = "feature_impact.json"
IMPACT_SVG = "feature_impact.svg"

FEATURE_GROUPS: dict[str, list[str]] = {
    "nlp_tactical": [
        "sectional_composite",
        "finishing_burst_level",
        "nlp_pace_rank",
        "nlp_pace_vs_field",
    ],
    "combo_priors": [
        "combo_bayes_win",
        "combo_bayes_place",
        "combo_prior_rides",
        "combo_vs_field",
        "hidden_potential",
    ],
    "entity_priors": [
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
    ],
    "cd_priors": [
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
    ],
    "ratings": ["official_rating", "rpr", "or_vs_field", "rpr_vs_field"],
    "course_draw": ["draw_bias_z", "days_since_last_run"],
}


def impact_artifact_paths(cfg: dict | None = None) -> tuple[Path, Path]:
    md = model_dir(cfg)
    return md / IMPACT_JSON, md / IMPACT_SVG


def _try_shap_importance(
    booster,
    frame: pd.DataFrame,
    features: list[str],
    *,
    max_samples: int = 800,
) -> dict[str, float] | None:
    try:
        import shap
    except ImportError:
        return None

    x = frame[features].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    if x.empty:
        return None
    sample = x.sample(min(len(x), max_samples), random_state=42) if len(x) > max_samples else x
    try:
        explainer = shap.TreeExplainer(booster)
        values = explainer.shap_values(sample)
        if isinstance(values, list):
            values = values[-1] if values else values
        arr = np.asarray(values)
        if arr.ndim != 2:
            return None
        mean_abs = np.abs(arr).mean(axis=0)
        return {features[i]: float(mean_abs[i]) for i in range(min(len(features), len(mean_abs)))}
    except Exception:
        return None


def _group_lift(rows: list[FeatureImportanceRow], shap: dict[str, float] | None) -> dict[str, dict]:
    by_name = {r.feature: r for r in rows}
    out: dict[str, dict] = {}
    for group, names in FEATURE_GROUPS.items():
        gain_pct = sum(by_name[n].gain_pct for n in names if n in by_name)
        shap_pct = None
        if shap:
            total = sum(shap.values()) or 1.0
            shap_pct = round(100.0 * sum(shap.get(n, 0.0) for n in names) / total, 2)
        out[group] = {
            "features": [n for n in names if n in by_name],
            "gain_lift_pct": round(float(gain_pct), 2),
            "shap_lift_pct": shap_pct,
        }
    return out


def render_importance_svg(rows: list[FeatureImportanceRow], *, width: int = 720, bar_h: int = 22) -> str:
    """Horizontal bar chart SVG — no matplotlib dependency."""
    top = rows[:12]
    if not top:
        return '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="40"><text x="8" y="24" fill="#94a3b8">No feature data</text></svg>'

    max_pct = max(r.gain_pct for r in top) or 1.0
    height = 48 + len(top) * (bar_h + 8)
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#0a1628" rx="8"/>',
        '<text x="16" y="26" fill="#b7f7c8" font-family="Inter,sans-serif" font-size="14" font-weight="700">Feature Impact (LightGBM gain %)</text>',
    ]
    label_w = 160
    chart_w = width - label_w - 80
    y = 44
    for row in top:
        bw = max(2, int(chart_w * (row.gain_pct / max_pct)))
        color = "#007A33" if row.feature in FEATURE_GROUPS["nlp_tactical"] else "#3b82f6"
        if row.feature.startswith("combo"):
            color = "#f6d889"
        lines.append(
            f'<text x="16" y="{y + 15}" fill="#cbd5e1" font-family="Inter,sans-serif" font-size="11">{row.feature}</text>'
        )
        lines.append(f'<rect x="{label_w}" y="{y}" width="{bw}" height="{bar_h}" fill="{color}" rx="4"/>')
        lines.append(
            f'<text x="{label_w + bw + 8}" y="{y + 15}" fill="#86efac" font-family="monospace" font-size="11">{row.gain_pct:.1f}%</text>'
        )
        y += bar_h + 8
    lines.append("</svg>")
    return "\n".join(lines)


def export_feature_impact_artifacts(
    booster,
    train_frame: pd.DataFrame,
    features: list[str],
    *,
    config_path: Path | None = None,
) -> dict[str, Any]:
    """
    Called automatically after train-ranker.
    Writes feature_impact.json + feature_impact.svg for the Status page.
    """
    cfg = load_config(config_path)
    json_path, svg_path = impact_artifact_paths(cfg)

    gain_rows = build_feature_importance_matrix(config_path=config_path)
    shap = _try_shap_importance(booster, train_frame, features)
    shap_rows: list[dict] = []
    if shap:
        total = sum(shap.values()) or 1.0
        ranked = sorted(shap.items(), key=lambda kv: kv[1], reverse=True)
        for i, (name, val) in enumerate(ranked, start=1):
            shap_rows.append({"rank": i, "feature": name, "mean_abs_shap": round(val, 6), "shap_pct": round(100 * val / total, 2)})

    holdout = _holdout_metrics(config_path)
    report: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "model_path": str(ranker_model_path(cfg)),
        "method": "shap+lightgbm" if shap else "lightgbm_gain",
        "matrix": [r.to_dict() for r in gain_rows],
        "shap_matrix": shap_rows,
        "group_lift": _group_lift(gain_rows, shap),
        "top_drivers": [r.feature for r in gain_rows[:5]],
        "nlp_features": FEATURE_GROUPS["nlp_tactical"],
        "holdout": holdout,
        "tuning_hints": _tuning_hints(gain_rows, shap),
    }

    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    svg_path.write_text(render_importance_svg(gain_rows), encoding="utf-8")
    report["json_path"] = str(json_path)
    report["svg_path"] = str(svg_path)
    return report


def _tuning_hints(rows: list[FeatureImportanceRow], shap: dict[str, float] | None) -> list[str]:
    by_name = {r.feature: r for r in rows}
    hints: list[str] = []
    nlp_pct = sum(by_name[f].gain_pct for f in FEATURE_GROUPS["nlp_tactical"] if f in by_name)
    combo_pct = sum(by_name[f].gain_pct for f in FEATURE_GROUPS["combo_priors"] if f in by_name)
    if nlp_pct >= 8:
        hints.append(
            f"NLP tactical block contributes {nlp_pct:.1f}% gain — finishing_burst / sectional signals are real edge."
        )
    if combo_pct >= 15 and by_name.get("combo_prior_rides", FeatureImportanceRow("", 0, 0, 0, 0, 99)).gain_pct < 1:
        hints.append("Combo priors dominate but combo_prior_rides is weak — consider raising combo_alpha smoothing in summer.")
    if by_name.get("finishing_burst_level") and by_name["finishing_burst_level"].gain_pct >= 0.5:
        hints.append(
            f"finishing_burst_level gain {by_name['finishing_burst_level'].gain_pct:.1f}% — validate vs keyword overfit with SHAP."
        )
    if not shap:
        hints.append("Install shap (pip install shap) for SHAP validation on next train-ranker run.")
    return hints


def load_feature_impact_report(cfg: dict | None = None) -> dict[str, Any] | None:
    json_path, svg_path = impact_artifact_paths(cfg)
    if not json_path.exists():
        return None
    try:
        report = json.loads(json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    report["svg_available"] = svg_path.exists()
    report["svg_path"] = str(svg_path)
    return report
