"""Data quality target helpers for racing (mirrors hibs-bet data_quality_targets)."""

from __future__ import annotations

import os


def _env_float(name: str, default: float) -> float:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def racing_data_quality_target_pct() -> float:
    return max(0.0, min(100.0, _env_float("HIBS_RACING_TARGET_DQ_PCT", 95.0)))


def racing_thin_rescue_dq_pct() -> float:
    return max(0.0, min(100.0, _env_float("HIBS_RACING_THIN_RESCUE_DQ_PCT", 90.0)))


def racing_rescue_max_per_cycle() -> int:
    try:
        return max(1, int(os.getenv("HIBS_RACING_RESCUE_MAX", "64")))
    except ValueError:
        return 64


def racing_enrich_recovery_min_pct() -> float:
    return max(0.0, min(100.0, _env_float("HIBS_RACING_ENRICH_RECOVERY_MIN_PCT", 95.0)))


def racing_engine_output_min_dq_pct() -> float:
    """Minimum runner DQ for engine picks / value gates (default 90%)."""
    return max(0.0, min(100.0, _env_float("HIBS_ENGINE_OUTPUT_MIN_DQ_PCT", 90.0)))
