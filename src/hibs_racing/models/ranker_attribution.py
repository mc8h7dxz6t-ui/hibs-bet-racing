from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from hibs_racing.cards.store import load_upcoming_runners
from hibs_racing.config import db_path, load_config, ranker_feature_path, ranker_model_path
from hibs_racing.features.ranker_matrix import build_card_feature_frame, ranker_feature_columns
from hibs_racing.models.feature_impact import FEATURE_GROUPS, _try_shap_importance
from hibs_racing.models.feature_importance import FeatureImportanceRow, build_feature_importance_matrix
from hibs_racing.models.lgbm_ranker import load_ranker, load_ranker_features

CD_FEATURES = FEATURE_GROUPS["cd_priors"]


def _booster_feature_names(booster) -> list[str]:
    try:
        names = booster.feature_name()
        return list(names) if names else []
    except Exception:
        return []


def verify_feature_manifest(
    manifest: list[str],
    booster_names: list[str],
) -> dict[str, Any]:
    manifest_set = set(manifest)
    booster_set = set(booster_names)
    missing_in_model = sorted(manifest_set - booster_set)
    extra_in_model = sorted(booster_set - manifest_set)
    order_match = manifest == booster_names if booster_names else False
    ok = not missing_in_model and not extra_in_model and order_match and bool(manifest)
    return {
        "ok": ok,
        "manifest_count": len(manifest),
        "booster_count": len(booster_names),
        "order_match": order_match,
        "missing_in_model": missing_in_model,
        "extra_in_model": extra_in_model,
    }


def _card_feature_sample(*, max_rows: int = 400) -> tuple[pd.DataFrame, int]:
    db = db_path(load_config())
    cards = load_upcoming_runners(db)
    if cards.empty:
        return pd.DataFrame(), 0
    frame = build_card_feature_frame(cards, database=db)
    n = len(frame)
    if n > max_rows:
        frame = frame.sample(max_rows, random_state=42)
    return frame, n


def _merge_attribution_rows(
    gain_rows: list[FeatureImportanceRow],
    shap: dict[str, float] | None,
) -> list[dict[str, Any]]:
    shap_total = sum(shap.values()) if shap else 0.0
    by_gain = {r.feature: r for r in gain_rows}
    features = [r.feature for r in gain_rows]
    if shap:
        for name in shap:
            if name not in by_gain:
                features.append(name)

    out: list[dict[str, Any]] = []
    for name in features:
        row = by_gain.get(name)
        gain_pct = round(row.gain_pct, 2) if row else 0.0
        shap_val = shap.get(name) if shap else None
        shap_pct = round(100.0 * shap_val / shap_total, 2) if shap and shap_val is not None and shap_total else None
        out.append(
            {
                "feature": name,
                "gain_pct": gain_pct,
                "shap_pct": shap_pct,
                "mean_abs_shap": round(shap_val, 6) if shap_val is not None else None,
                "in_cd_block": name in CD_FEATURES,
            }
        )
    out.sort(key=lambda r: (r["gain_pct"], r["shap_pct"] or 0.0), reverse=True)
    for i, row in enumerate(out, start=1):
        row["rank"] = i
    return out


def _verification_checks(
    *,
    manifest: list[str],
    manifest_check: dict[str, Any],
    card_rows: int,
    shap: dict[str, float] | None,
    card_frame: pd.DataFrame,
) -> list[dict[str, str]]:
    checks: list[dict[str, str]] = []

    def add(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "status": "pass" if ok else "fail", "detail": detail})

    add(
        "feature_manifest",
        manifest_check.get("ok", False),
        f"{manifest_check.get('manifest_count', 0)} features · order_match={manifest_check.get('order_match')}",
    )
    cd_in_manifest = [f for f in CD_FEATURES if f in manifest]
    add(
        "cd_entity_block",
        len(cd_in_manifest) >= 8,
        f"{len(cd_in_manifest)}/{len(CD_FEATURES)} CD/CDD features in manifest",
    )
    add(
        "live_card_sample",
        card_rows > 0,
        f"{card_rows} runners on card" if card_rows else "No card loaded — refresh 24h window",
    )
    if card_rows > 0 and manifest:
        present = sum(1 for f in manifest if f in card_frame.columns)
        add(
            "card_feature_coverage",
            present == len(manifest),
            f"{present}/{len(manifest)} manifest features present on live card frame",
        )
    add(
        "shap_attribution",
        shap is not None,
        "SHAP computed on live card sample" if shap else "SHAP unavailable (install shap or load card)",
    )
    return checks


def live_ranker_attribution(
    *,
    config_path: Path | None = None,
    max_shap_samples: int = 400,
) -> dict[str, Any]:
    """
    Real-time ranker verification for /status:
    - parity check: lgbm_ranker_features.json vs booster.feature_name()
    - LightGBM gain % from saved booster
    - SHAP mean |value| on current upcoming card (when runners loaded)
    """
    cfg = load_config(config_path)
    fp = ranker_feature_path(cfg)
    mp = ranker_model_path(cfg)

    manifest: list[str] = []
    if fp.exists():
        try:
            manifest = load_ranker_features(fp)
        except (json.JSONDecodeError, OSError):
            manifest = []
    if not manifest:
        manifest = ranker_feature_columns()

    booster = load_ranker(mp)
    booster_names = _booster_feature_names(booster) if booster else []
    manifest_check = verify_feature_manifest(manifest, booster_names)

    gain_rows: list[FeatureImportanceRow] = []
    if booster is not None:
        try:
            gain_rows = build_feature_importance_matrix(
                model_path=mp,
                feature_path=fp,
                config_path=config_path,
            )
        except FileNotFoundError:
            gain_rows = []

    card_frame, card_rows = _card_feature_sample(max_rows=max_shap_samples)
    shap: dict[str, float] | None = None
    shap_source = "none"
    if booster is not None and not card_frame.empty:
        shap = _try_shap_importance(booster, card_frame, manifest, max_samples=max_shap_samples)
        if shap:
            shap_source = "live_card"
    if shap is None and booster is not None:
        try:
            from hibs_racing.features.ranker_matrix import build_ranker_matrix

            matrix = build_ranker_matrix(export_parquet=False, config_path=config_path)
            if not matrix.empty:
                shap = _try_shap_importance(booster, matrix, manifest, max_samples=max_shap_samples)
                if shap:
                    shap_source = "holdout_matrix"
        except Exception:
            pass

    matrix = _merge_attribution_rows(gain_rows, shap)
    checks = _verification_checks(
        manifest=manifest,
        manifest_check=manifest_check,
        card_rows=card_rows,
        shap=shap,
        card_frame=card_frame,
    )
    all_pass = all(c["status"] == "pass" for c in checks if c["name"] != "shap_attribution")
    shap_pass = any(c["name"] == "shap_attribution" and c["status"] == "pass" for c in checks)

    return {
        "ok": all_pass and shap_pass,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "model_path": str(mp),
        "feature_path": str(fp),
        "model_loaded": booster is not None,
        "feature_count": len(manifest),
        "manifest_features": manifest,
        "manifest_check": manifest_check,
        "method": "shap+lightgbm" if shap else "lightgbm_gain",
        "shap_source": shap_source,
        "card_sample_rows": card_rows,
        "checks": checks,
        "matrix": matrix,
        "top_drivers": [r["feature"] for r in matrix[:5]],
        "cd_block_pct_gain": round(
            sum(r["gain_pct"] for r in matrix if r["feature"] in CD_FEATURES),
            2,
        ),
    }
