"""Pinned ranker manifest — content hash independent of filesystem mtime."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hibs_racing.config import load_config, model_dir


def ranker_manifest_path(cfg: dict | None = None) -> Path:
    cfg = cfg or load_config()
    fname = cfg.get("ranker", {}).get("manifest_file", "ranker_manifest.json")
    return model_dir(cfg) / fname


def compute_stable_hash(
    *,
    features: list[str],
    ranker_tier: str,
    holdout_top1: float | None,
) -> str:
    payload = {
        "features": sorted(features),
        "ranker_tier": ranker_tier,
        "holdout_top1": round(holdout_top1, 6) if holdout_top1 is not None else None,
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
    return digest[:16]


def write_ranker_manifest(
    *,
    features: list[str],
    ranker_tier: str,
    holdout_top1: float | None,
    enrich_coverage: dict[str, float] | None = None,
    metrics: dict[str, Any] | None = None,
    config_path: Path | None = None,
) -> dict[str, Any]:
    cfg = load_config(config_path)
    stable_hash = compute_stable_hash(
        features=features,
        ranker_tier=ranker_tier,
        holdout_top1=holdout_top1,
    )
    manifest: dict[str, Any] = {
        "stable_hash": stable_hash,
        "ranker_tier": ranker_tier,
        "feature_count": len(features),
        "features": features,
        "holdout_top1_hit_rate": holdout_top1,
        "enrich_coverage_pct": enrich_coverage,
        "metrics": metrics or {},
        "pinned_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }
    path = ranker_manifest_path(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    manifest["manifest_path"] = str(path)
    return manifest


def load_ranker_manifest(cfg: dict | None = None) -> dict[str, Any] | None:
    path = ranker_manifest_path(cfg)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def model_version_stamp(cfg: dict | None = None) -> str:
    """Prefer pinned manifest hash; fall back to booster mtime."""
    cfg = cfg or load_config()
    manifest = load_ranker_manifest(cfg)
    if manifest and manifest.get("stable_hash"):
        tier = manifest.get("ranker_tier", "base")
        return f"manifest:{tier}:{manifest['stable_hash']}"
    ranker = cfg.get("ranker", {})
    model_file = str(ranker.get("model_file", "lgbm_ranker.txt"))
    path = model_dir(cfg) / model_file
    if path.exists():
        return f"{model_file}:{int(path.stat().st_mtime)}"
    return model_file
