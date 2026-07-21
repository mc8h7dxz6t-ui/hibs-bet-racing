"""Racing lane visibility — explain why value/sniper/place/win panels are empty."""

from __future__ import annotations

from typing import Any


def build_racing_lanes_status(
    *,
    health: Any,
    value_lane_picks: list[dict] | None,
    sniper_lane_picks: list[dict] | None,
    engine_top_picks: list[dict] | None = None,
    value_count: int = 0,
    runner_count: int = 0,
    ui_data_status: dict | None = None,
) -> dict[str, Any]:
    """Summary for dashboard/insights — always surface lane state (even when pick lists empty)."""
    vl = list(value_lane_picks or [])
    sl = list(sniper_lane_picks or [])
    ep = list(engine_top_picks or [])
    ui = ui_data_status or {}

    blockers: list[str] = []
    if health is not None:
        raw = getattr(health, "value_lane_blockers", None)
        if raw is None and isinstance(health, dict):
            raw = health.get("value_lane_blockers")
        if raw:
            blockers = list(raw)

    matchbook = _health_bool(health, "matchbook")
    racing_api = _health_bool(health, "racing_api")
    lane_ready = _health_bool(health, "value_lane_ready")
    prod_n = _health_int(health, "production_value_count")

    win = _win_engine_lane_status()

    hints: list[str] = []
    if not racing_api:
        hints.append("Set RACING_API_* in /opt/hibs-racing/.env for cards.")
    if not matchbook:
        hints.append("Set MATCHBOOK_USER + MATCHBOOK_PASSWORD for exchange odds and value EV.")
    elif lane_ready and not vl and value_count == 0:
        hints.append("Cards scored but no value_flag runners — run Refresh 24h after Matchbook poll.")
    elif lane_ready and not vl and value_count > 0:
        hints.append(f"{value_count} raw value flags gated — see Card stats for block rate.")
    if lane_ready and not sl and vl:
        hints.append("Value picks exist but none pass Gate7 (OR≥65, RTF≥20) for sniper lane.")
    if runner_count > 0 and not ep:
        hints.append("Place engine: score cards to populate model_place_prob.")
    if not win["public_release"]:
        hints.append(win["status_note"])

    return {
        "value_lane_count": len(vl),
        "sniper_lane_count": len(sl),
        "place_engine_count": len(ep),
        "raw_value_count": int(value_count),
        "runner_count": int(runner_count),
        "value_lane_ready": lane_ready,
        "value_lane_blockers": blockers,
        "matchbook": matchbook,
        "racing_api": racing_api,
        "production_value_count": prod_n,
        "odds_coverage": ui.get("odds_coverage"),
        "win_engine": win,
        "hints": hints,
    }


def _health_bool(health: Any, key: str) -> bool:
    if health is None:
        return False
    if isinstance(health, dict):
        return bool(health.get(key))
    return bool(getattr(health, key, False))


def _health_int(health: Any, key: str) -> int | None:
    if health is None:
        return None
    if isinstance(health, dict):
        val = health.get(key)
    else:
        val = getattr(health, key, None)
    if val is None:
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _win_engine_lane_status() -> dict[str, Any]:
    try:
        from hibs_racing.config import db_path, load_config
        from hibs_racing.features.store import connect
        from hibs_racing.models.win_engine_config import (
            win_engine_active,
            win_engine_env_requested,
            win_engine_public_release_allowed,
        )
        from hibs_racing.models.win_engine_store import ensure_win_engine_schema, load_calibration_state

        env_on = win_engine_env_requested()
        active = win_engine_active()
        public = win_engine_public_release_allowed()
        db = db_path(load_config())
        ensure_win_engine_schema(db)
        with connect(db) as conn:
            cal = load_calibration_state(conn)
        state = str(cal.get("calibration_state") or "UNKNOWN")
        sample_n = int(cal.get("sample_n") or 0)
        races = int(cal.get("races_in_window") or 0)
    except Exception:
        return {
            "env_requested": False,
            "active": False,
            "public_release": False,
            "calibration_state": "UNKNOWN",
            "sample_n": 0,
            "status_note": "Win engine staging — set HIBS_WIN_ENGINE_ACTIVE after calibration (see WIN_ENGINE_DEPLOYMENT.md).",
        }

    if public:
        note = "Win engine live — McFadden win probs on combinations API."
    elif active:
        note = "Win engine active internally; public release pending calibration checks."
    elif env_on:
        note = f"Win engine env on but not calibrated ({state}, n={sample_n}, races={races})."
    else:
        note = "Win engine off — run apply-win-engine-env.sh then calibrate before go-live."

    return {
        "env_requested": env_on,
        "active": active,
        "public_release": public,
        "calibration_state": state,
        "sample_n": sample_n,
        "races_in_window": races,
        "status_note": note,
    }
