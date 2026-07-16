from __future__ import annotations

import os

CALIBRATION_CALIBRATED = "CALIBRATED"
CALIBRATION_UNCALIBRATED = "UNCALIBRATED"


def _env_flag(name: str, default: bool = False) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


def win_engine_active() -> bool:
    return _env_flag("HIBS_WIN_ENGINE_ACTIVE", default=False)


def win_brier_pass_max() -> float:
    try:
        return float(os.environ.get("HIBS_RACING_WIN_BRIER_PASS_MAX", "0.185"))
    except ValueError:
        return 0.185


def min_win_calibration_n() -> int:
    try:
        return max(1, int(os.environ.get("HIBS_RACING_MIN_WIN_CALIBRATION_N", "100")))
    except ValueError:
        return 100


def win_engine_public_release_allowed() -> bool:
    """Frontend may receive win-engine fields only when active AND calibrated."""
    if not win_engine_active():
        return False
    return True
