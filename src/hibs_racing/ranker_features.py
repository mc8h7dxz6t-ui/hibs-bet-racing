from __future__ import annotations

import json
import os
from pathlib import Path

from hibs_racing.config import load_config, model_dir, ranker_feature_path, ranker_model_path


def ranker_enrich_feature_path(cfg: dict | None = None) -> Path:
    cfg = cfg or load_config()
    fname = cfg.get("ranker", {}).get("enrich_feature_file", "lgbm_ranker_features_enrich.json")
    return model_dir(cfg) / fname


def ranker_tracker_feature_path(cfg: dict | None = None) -> Path:
    cfg = cfg or load_config()
    fname = cfg.get("ranker", {}).get("tracker_feature_file", "lgbm_ranker_features_tracker.json")
    return model_dir(cfg) / fname


def _feature_count(path: Path) -> int | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        feats = payload if isinstance(payload, list) else payload.get("features")
        return len(feats) if feats else None
    except (OSError, json.JSONDecodeError, TypeError):
        return None


def _booster_feature_count(model_path: Path) -> int | None:
    if not model_path.exists():
        return None
    try:
        import lightgbm as lgb

        bst = lgb.Booster(model_file=str(model_path))
        names = bst.feature_name()
        return len(names) if names else None
    except (ImportError, OSError):
        return None


def resolve_ranker_feature_path(cfg: dict | None = None) -> Path:
    """
    Pick base vs enrich feature manifest without breaking existing models.

    auto (default): match LightGBM booster feature count to manifest length.
    true: prefer enrich manifest when file exists.
    false: always base manifest.
    """
    cfg = cfg or load_config()
    ranker_cfg = cfg.get("ranker", {})
    mode = os.environ.get("HIBS_USE_ENRICH_RANKER", "").strip().lower()
    if mode in {"1", "true", "yes", "on"}:
        use_enrich = "true"
    elif mode in {"0", "false", "no", "off"}:
        use_enrich = "false"
    else:
        use_enrich = str(ranker_cfg.get("use_enrich_features", "auto")).lower()

    base = ranker_feature_path(cfg)
    enrich = ranker_enrich_feature_path(cfg)
    tracker = ranker_tracker_feature_path(cfg)

    if use_enrich == "false":
        return base
    if use_enrich == "true":
        if tracker.exists() and _env_tracker_ranker_requested():
            return tracker
        return enrich if enrich.exists() else base

    model_path = ranker_model_path(cfg)
    n_model = _booster_feature_count(model_path)
    n_tracker = _feature_count(tracker)
    n_enrich = _feature_count(enrich)
    n_base = _feature_count(base)
    if n_model is not None and n_tracker is not None and n_model == n_tracker:
        return tracker
    if n_model is not None and n_enrich is not None and n_model == n_enrich:
        return enrich
    if n_model is not None and n_base is not None and n_model == n_base:
        return base
    if _env_tracker_ranker_requested() and tracker.exists():
        return tracker
    return base


def _env_tracker_ranker_requested() -> bool:
    raw = os.environ.get("HIBS_USE_TRACKER_RANKER", "").strip().lower()
    return raw in {"1", "true", "yes", "on", "live", "shadow", "auto"}


def ranker_feature_profile(cfg: dict | None = None) -> dict[str, object]:
    """Dashboard/status: which feature manifest matches the saved booster."""
    cfg = cfg or load_config()
    path = resolve_ranker_feature_path(cfg)
    n = _feature_count(path)
    enrich = ranker_enrich_feature_path(cfg)
    tracker = ranker_tracker_feature_path(cfg)
    return {
        "feature_manifest": path.name,
        "feature_count": n,
        "enrich_manifest_available": enrich.exists(),
        "tracker_manifest_available": tracker.exists(),
        "enrich_feature_count": _feature_count(enrich),
        "tracker_feature_count": _feature_count(tracker),
        "uses_enrich": path.name == enrich.name,
        "uses_tracker": path.name == tracker.name,
    }
