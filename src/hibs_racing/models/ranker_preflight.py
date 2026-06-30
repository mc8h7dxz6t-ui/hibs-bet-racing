"""Production ranker artifact verification — fail closed before scoring or cron."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from hibs_racing.config import load_config, ranker_model_path
from hibs_racing.models.ranker_manifest import load_ranker_manifest, ranker_manifest_path
from hibs_racing.ranker_features import resolve_ranker_feature_path


class RankerPreflightError(RuntimeError):
    """Raised when production ranker artifacts are missing or inconsistent."""


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_feature_names(feature_path: Path) -> list[str]:
    payload = json.loads(feature_path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [str(x) for x in payload]
    return [str(x) for x in (payload.get("features") or [])]


def verify_ranker_artifacts(
    *,
    model_path: Path,
    feature_path: Path,
    manifest_path: Path | None = None,
    require_manifest: bool = False,
) -> dict[str, Any]:
    """
    Verify ranker model + features exist and optionally match pinned manifest.

    Returns metadata for health APIs; raises RankerPreflightError on failure.
    """
    errors: list[str] = []
    if not model_path.is_file() or model_path.stat().st_size == 0:
        errors.append(f"missing or empty model: {model_path}")
    if not feature_path.is_file() or feature_path.stat().st_size == 0:
        errors.append(f"missing or empty features: {feature_path}")

    features: list[str] = []
    if not errors:
        try:
            features = _load_feature_names(feature_path)
            if not features:
                errors.append(f"empty feature list in {feature_path}")
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"invalid features JSON: {exc}")

    manifest: dict[str, Any] | None = None
    if manifest_path and manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"invalid manifest: {exc}")
    elif require_manifest:
        errors.append(f"missing manifest: {manifest_path}")

    if manifest and features:
        manifest_features = [str(x) for x in (manifest.get("features") or [])]
        if sorted(manifest_features) != sorted(features):
            errors.append("feature list mismatch vs ranker_manifest.json")

    if manifest and model_path.is_file():
        pinned_sha = str(manifest.get("model_sha256") or "").strip().lower()
        if pinned_sha:
            actual_sha = file_sha256(model_path)
            if actual_sha != pinned_sha:
                errors.append("model_sha256 mismatch vs ranker_manifest.json")

    if errors:
        raise RankerPreflightError(
            "CRITICAL: ranker preflight failed — "
            + "; ".join(errors)
            + ". Train/copy artifacts or set HIBS_RACING_PRODUCTION=0 for dev."
        )

    out: dict[str, Any] = {
        "ok": True,
        "model_path": str(model_path),
        "feature_path": str(feature_path),
        "feature_count": len(features),
    }
    if model_path.is_file():
        out["model_sha256"] = file_sha256(model_path)
        out["model_bytes"] = model_path.stat().st_size
    if manifest:
        out["manifest_stable_hash"] = manifest.get("stable_hash")
        out["ranker_tier"] = manifest.get("ranker_tier")
    return out


def verify_production_ranker(root: str | Path | None = None) -> dict[str, Any]:
    """Resolve default paths from config and verify (used by cron/Docker)."""
    cfg = load_config()
    base = Path(root) if root else Path(__file__).resolve().parents[3]
    mp = ranker_model_path(cfg)
    fp = resolve_ranker_feature_path(cfg)
    if not mp.is_absolute():
        mp = base / mp
    if not fp.is_absolute():
        fp = base / fp
    manifest = ranker_manifest_path(cfg)
    if not manifest.is_absolute():
        manifest = base / manifest
    require_manifest = os.environ.get("HIBS_RANKER_REQUIRE_MANIFEST", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    return verify_ranker_artifacts(
        model_path=mp,
        feature_path=fp,
        manifest_path=manifest,
        require_manifest=require_manifest,
    )


def is_production_mode() -> bool:
    return os.environ.get("HIBS_RACING_PRODUCTION", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def observation_lane_enabled() -> bool:
    """Production defaults to strict thresholds (observation lane off unless explicitly set)."""
    raw = os.environ.get("HIBS_OBSERVATION_LANE")
    if raw is None or not str(raw).strip():
        return not is_production_mode()
    return str(raw).strip().lower() in ("1", "true", "yes", "on")
