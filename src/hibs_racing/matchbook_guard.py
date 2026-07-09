"""Matchbook poll gate — rate limits, Mac/VPS owner, 429 circuit (hands-off safe)."""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

_log_once_lock = threading.Lock()
_logged_once: set[str] = set()


def _cache_dir() -> Path:
    raw = (os.getenv("HIBS_RACING_CACHE_DIR") or "data/.cache").strip()
    return Path(raw)


def _state_path() -> Path:
    return _cache_dir() / "matchbook_guard_v1.json"


def _load_state() -> Dict[str, Any]:
    path = _state_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_state(data: Dict[str, Any]) -> None:
    path = _state_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass


def _poll_interval_sec() -> float:
    try:
        from hibs_racing.config import load_config

        mb = load_config().get("matchbook") or {}
        return max(60.0, float(mb.get("poll_seconds", 120)))
    except Exception:
        return 120.0


def _trip_ttl_hours() -> float:
    try:
        return max(0.5, float(os.getenv("HIBS_MATCHBOOK_TRIP_TTL_HOURS", "2")))
    except ValueError:
        return 2.0


def matchbook_configured() -> bool:
    user = (os.getenv("MATCHBOOK_USERNAME") or os.getenv("MATCHBOOK_USER") or "").strip()
    password = (os.getenv("MATCHBOOK_PASSWORD") or "").strip()
    return bool(user and password)


def poll_owner() -> str:
    return (os.getenv("HIBS_MATCHBOOK_POLL_OWNER") or "vps").strip().lower()


def mac_quotes_fresh(*, max_age_hours: float = 3.0) -> bool:
    """True when Mac rsync'd sqlite or exchange_quotes recently (VPS should not poll)."""
    markers = [
        _cache_dir() / "mac_odds_publish.json",
        Path(os.getenv("HIBS_RACING_DATA_DIR", "data")) / "feature_store.sqlite",
    ]
    now = datetime.now(timezone.utc).timestamp()
    for path in markers:
        if not path.is_file():
            continue
        age_h = (now - path.stat().st_mtime) / 3600.0
        if age_h <= max_age_hours:
            return True
    return False


def global_trip_active() -> bool:
    data = _load_state()
    trip = data.get("trip")
    if not isinstance(trip, dict) or not trip.get("at"):
        return False
    try:
        at = datetime.fromisoformat(str(trip["at"]).replace("Z", "+00:00"))
        if at.tzinfo is None:
            at = at.replace(tzinfo=timezone.utc)
        age_h = (datetime.now(timezone.utc) - at).total_seconds() / 3600.0
        return age_h < _trip_ttl_hours()
    except (TypeError, ValueError):
        return False


def record_rate_limit(*, http_status: int = 429, reason: str = "") -> None:
    data = _load_state()
    data["trip"] = {
        "at": datetime.now(timezone.utc).isoformat(),
        "status": http_status,
        "reason": (reason or "")[:120],
    }
    data["failure_count"] = int(data.get("failure_count") or 0) + 1
    _save_state(data)
    _log_once("trip", f"[Matchbook] rate limit / error ({http_status}) — pause {_trip_ttl_hours():.1f}h")


def record_poll_success() -> None:
    data = _load_state()
    data["last_poll_at"] = datetime.now(timezone.utc).isoformat()
    data.pop("trip", None)
    _save_state(data)


def matchbook_traffic_allowed(*, force: bool = False) -> bool:
    if force:
        return matchbook_configured()
    if os.getenv("HIBS_SKIP_MATCHBOOK", "").strip().lower() in ("1", "true", "yes", "on"):
        return False
    if not matchbook_configured():
        return False
    if global_trip_active():
        return False
    owner = poll_owner()
    if owner == "mac" and mac_quotes_fresh():
        return False
    if owner == "vps" and mac_quotes_fresh() and os.getenv("HIBS_MATCHBOOK_VPS_OVERRIDE", "").lower() not in (
        "1",
        "true",
        "yes",
    ):
        # Mac published odds recently — defer VPS poll (single writer).
        return False
    data = _load_state()
    last = data.get("last_poll_at")
    if last:
        try:
            at = datetime.fromisoformat(str(last).replace("Z", "+00:00"))
            if at.tzinfo is None:
                at = at.replace(tzinfo=timezone.utc)
            age_s = (datetime.now(timezone.utc) - at).total_seconds()
            if age_s < _poll_interval_sec():
                return False
        except (TypeError, ValueError):
            pass
    return True


def status_payload() -> Dict[str, Any]:
    data = _load_state()
    return {
        "traffic_allowed": matchbook_traffic_allowed(),
        "configured": matchbook_configured(),
        "poll_owner": poll_owner(),
        "mac_quotes_fresh": mac_quotes_fresh(),
        "global_trip": global_trip_active(),
        "last_poll_at": data.get("last_poll_at"),
        "trip": data.get("trip"),
        "poll_interval_sec": _poll_interval_sec(),
    }


def _log_once(key: str, message: str) -> None:
    with _log_once_lock:
        if key in _logged_once:
            return
        _logged_once.add(key)
    print(message)
