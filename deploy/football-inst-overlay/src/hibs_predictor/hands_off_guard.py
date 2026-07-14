"""Safe hands-off automation — rate limits, locks, non-degrading repairs."""

from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator

_DEFAULT_STATE = Path("/opt/hibs-bet/.cache/hands_off_state.json")
_LOCK_DIR = Path("/var/run/hibs-bet")


def _state_path() -> Path:
    raw = (os.getenv("HIBS_HANDS_OFF_STATE") or "").strip()
    if raw:
        return Path(raw)
    app = (os.getenv("DEPLOY_PATH") or os.getenv("HOME") or "/opt/hibs-bet").strip()
    return Path(app) / ".cache" / "hands_off_state.json"


def _load_state() -> dict[str, Any]:
    path = _state_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_state(state: dict[str, Any]) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")


def _utc_now() -> float:
    return datetime.now(timezone.utc).timestamp()


def _hours_since(iso_or_ts: Any) -> float | None:
    if iso_or_ts is None:
        return None
    try:
        if isinstance(iso_or_ts, (int, float)):
            return (_utc_now() - float(iso_or_ts)) / 3600.0
        text = str(iso_or_ts).replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (_utc_now() - dt.timestamp()) / 3600.0
    except Exception:
        return None


def rate_limit_ok(key: str, *, min_hours: float) -> bool:
    """True if action `key` has not run within min_hours."""
    state = _load_state()
    row = state.get(key) or {}
    age = _hours_since(row.get("last_ts"))
    if age is None:
        return True
    return age >= float(min_hours)


def record_action(key: str, *, extra: dict[str, Any] | None = None) -> None:
    state = _load_state()
    row: dict[str, Any] = {"last_ts": _utc_now(), "last_iso": datetime.now(timezone.utc).isoformat()}
    if extra:
        row.update(extra)
    state[key] = row
    _save_state(state)


def service_restart_allowed(unit: str, *, min_minutes: float = 60.0) -> bool:
    key = f"restart:{unit}"
    state = _load_state()
    age_h = _hours_since((state.get(key) or {}).get("last_ts"))
    if age_h is not None and age_h < (min_minutes / 60.0):
        return False
    record_action(key)
    return True


def should_seed_forward(*, capture_pct: float | None, min_hours: float = 4.0) -> bool:
    """
    Seed snapshots when capture is below gate and we have not seeded recently.
    Never seeds more than 4× per day (6h minimum gap default).
    """
    if not rate_limit_ok("seed_forward", min_hours=min_hours):
        return False
    daily = _load_state().get("seed_forward_daily") or {}
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if int(daily.get(day) or 0) >= 4:
        return False
    if capture_pct is None:
        return True
    return float(capture_pct) < 50.0


def record_seed_forward() -> None:
    record_action("seed_forward")
    state = _load_state()
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    daily = state.get("seed_forward_daily") or {}
    daily[day] = int(daily.get(day) or 0) + 1
    state["seed_forward_daily"] = daily
    _save_state(state)


@contextmanager
def flock(name: str, *, blocking: bool = False) -> Generator[bool, None, None]:
    """Process lock under /var/run/hibs-bet — returns acquired bool."""
    try:
        import fcntl
    except ImportError:
        yield True
        return

    _LOCK_DIR.mkdir(parents=True, exist_ok=True)
    lock_path = _LOCK_DIR / f"{name}.lock"
    handle = lock_path.open("w")
    flags = fcntl.LOCK_EX if blocking else fcntl.LOCK_EX | fcntl.LOCK_NB
    acquired = False
    try:
        try:
            fcntl.flock(handle.fileno(), flags)
            acquired = True
        except BlockingIOError:
            acquired = False
        yield acquired
    finally:
        if acquired:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            except Exception:
                pass
        handle.close()


def trading_shadow_hard_stop() -> bool:
    """True when Day-15 FAIL / ops mandate: do not restart trading-shadow-soak."""
    raw = (os.getenv("HIBS_TRADING_SHADOW_HARD_STOP") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def capture_pct_7d() -> float | None:
    try:
        from hibs_predictor.prediction_log import audit_odds_capture_stats

        cap = audit_odds_capture_stats(days=7)
        val = cap.get("capture_rate_pct")
        return float(val) if val is not None else None
    except Exception:
        return None
