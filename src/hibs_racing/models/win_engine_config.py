from __future__ import annotations

import os

CALIBRATION_CALIBRATED = "CALIBRATED"
CALIBRATION_UNCALIBRATED = "UNCALIBRATED"


def _env_flag(name: str, default: bool = False) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


def _env_float(name: str, default: float) -> float:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        return max(1, int(raw))
    except ValueError:
        return default


def win_engine_env_requested() -> bool:
    """Raw env flag — may be true while calibration gate still blocks execution."""
    return _env_flag("HIBS_WIN_ENGINE_ACTIVE", default=False)


def max_absolute_brier_small_field() -> float:
    return _env_float("HIBS_RACING_MAX_ABSOLUTE_BRIER_SMALL_FIELD", 0.280)


def max_absolute_brier_large_field() -> float:
    return _env_float("HIBS_RACING_MAX_ABSOLUTE_BRIER_LARGE_FIELD", 0.075)


def min_market_beat_bps() -> int:
    return _env_int("HIBS_RACING_MIN_MARKET_BEAT_BPS", 150)


def min_win_calibration_n() -> int:
    """Minimum settled races required before CALIBRATED state is allowed."""
    return _env_int("HIBS_RACING_MIN_WIN_CALIBRATION_N", 500)


def win_brier_pass_max() -> float:
    """Legacy flat ceiling — retained for backtest reporting only."""
    return _env_float("HIBS_RACING_WIN_BRIER_PASS_MAX", 0.185)


def max_brier_for_field_size(field_size: int) -> float:
    """
    Adaptive per-race multiclass Brier ceiling by runner count M.
    M <= 6: small-field cap; 7..11: linear slide; M >= 12: large-field cap.
    """
    m = max(1, int(field_size))
    small_cap = max_absolute_brier_small_field()
    large_cap = max_absolute_brier_large_field()
    if m <= 6:
        return small_cap
    if m <= 11:
        return small_cap - ((m - 6) * 0.041)
    return large_cap


def _calibration_gate_passes() -> bool:
    """Fail-closed: CALIBRATED state, variable bounds, market beat, minimum race N."""
    from hibs_racing.config import db_path, load_config
    from hibs_racing.features.store import connect
    from hibs_racing.models.win_engine_store import ensure_win_engine_schema, load_calibration_state

    db = db_path(load_config())
    ensure_win_engine_schema(db)
    with connect(db) as conn:
        state = load_calibration_state(conn)
    if state.get("calibration_state") != CALIBRATION_CALIBRATED:
        return False
    if int(state.get("races_in_window") or 0) < min_win_calibration_n():
        return False
    if int(state.get("sample_n") or 0) < min_win_calibration_n():
        return False
    if not state.get("variable_bounds_pass"):
        return False
    if not state.get("market_beat_pass"):
        return False
    return True


def win_engine_active() -> bool:
    """Effective active — env flag AND calibration gate must pass."""
    if not win_engine_env_requested():
        return False
    return _calibration_gate_passes()


def win_engine_public_release_allowed() -> bool:
    """Frontend may receive win-engine fields only when active AND calibrated."""
    if not win_engine_active():
        return False
    return True
