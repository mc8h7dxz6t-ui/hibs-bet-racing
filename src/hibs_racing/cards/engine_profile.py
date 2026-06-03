"""Institutional engine identity — ranker tier + Harville/EW profile for manifests."""

from __future__ import annotations

from typing import Any

from hibs_racing.cards.harville_config import harville_runtime_config
from hibs_racing.config import load_config
from hibs_racing.ranker_features import ranker_feature_profile


def build_engine_profile(cfg: dict | None = None) -> dict[str, Any]:
    """
    Snapshot of which ranker manifest is active (36 base vs 48 enrich) and pricing knobs.
    Call before changing enrich booster or Harville env.
    """
    cfg = cfg or load_config()
    ranker = ranker_feature_profile(cfg)
    harville = harville_runtime_config(cfg)
    uses_enrich = bool(ranker.get("uses_enrich"))
    count = ranker.get("feature_count")
    tier = "enrich_48" if uses_enrich else "base_36"
    warning = None
    if ranker.get("enrich_manifest_available") and not uses_enrich:
        warning = (
            "Enrich feature manifest exists but booster uses base features — "
            "enrich stats feed gates/DQ only until train-ranker --with-enrich."
        )
    return {
        "ranker_tier": tier,
        "ranker_feature_manifest": ranker.get("feature_manifest"),
        "ranker_feature_count": count,
        "uses_enrich_booster": uses_enrich,
        "enrich_manifest_available": ranker.get("enrich_manifest_available"),
        "enrich_feature_count": ranker.get("enrich_feature_count"),
        "harville": harville,
        "warning": warning,
    }
