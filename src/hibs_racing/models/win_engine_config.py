from __future__ import annotations

import os

CALIBRATION_CALIBRATED = "CALIBRATED"
CALIBRATION_UNCALIBRATED = "UNCALIBRATED"


def _env_flag(name: str, default: bool = False) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


def win_engine_env_requested() -> bool:
    """Raw env flag — may be true while calibration gate still blocks execution."""
    return _env_flag("HIBS_WIN_ENGINE_ACTIVE", default=False)


def _calibration_gate_passes() -> bool:
    """Fail-closed: CALIBRATED state, Brier under threshold, minimum sample N."""
    from hibs_racing.config import db_path, load_config
    from hibs_racing.features.store import connect
    from hibs_racing.models.win_engine_store import ensure_win_engine_schema, load_calibration_state

    db = db_path(load_config())
    ensure_win_engine_schema(db)
    with connect(db) as conn:
        state = load_calibration_state(conn)
    if state.get("calibration_state") != CALIBRATION_CALIBRATED:
        return False
    brier = state.get("rolling_brier")
    if brier is not None and float(brier) > win_brier_pass_max():
        return False
    if int(state.get("sample_n") or 0) < min_win_calibration_n():
        return False
    return True


def win_engine_active() -> bool:
    """Effective active — env flag AND calibration gate must pass."""
    if not win_engine_env_requested():
        return False
    return _calibration_gate_passes()


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
