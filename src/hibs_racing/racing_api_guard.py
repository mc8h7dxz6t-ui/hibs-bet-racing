"""Racing API 401/403/429 guard — circuit + rpscrape fallback when API is blocked."""

from __future__ import annotations

import os
import threading
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Set

_log_once_lock = threading.Lock()
_logged_once: Set[str] = set()


def _state_path() -> str:
    cache = os.getenv("HIBS_RACING_CACHE_DIR", "data/.cache")
    return f"{cache}/racing_api_guard_v1.json"


def _load_state() -> Dict[str, Any]:
    import json
    from pathlib import Path

    path = Path(_state_path())
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_state(data: Dict[str, Any]) -> None:
    import json
    from pathlib import Path

    path = Path(_state_path())
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass


def _block_ttl_hours() -> float:
    try:
        return max(1.0, float(os.getenv("HIBS_RACING_API_FORBIDDEN_TTL_HOURS", "6")))
    except ValueError:
        return 6.0


def record_forbidden(*, http_status: int = 403, reason: str = "") -> None:
    data = _load_state()
    data["forbidden"] = {
        "at": datetime.now(timezone.utc).isoformat(),
        "status": http_status,
        "reason": (reason or "")[:160],
    }
    data["failure_count"] = int(data.get("failure_count") or 0) + 1
    _save_state(data)
    _log_once(
        f"forbidden:{http_status}",
        f"[Racing API] blocked ({http_status}) — use rpscrape fallback for {_block_ttl_hours():.0f}h",
    )
    threshold = 3
    try:
        threshold = max(1, int(os.getenv("HIBS_RACING_API_GLOBAL_TRIP_AFTER", "3")))
    except ValueError:
        pass
    if int(data.get("failure_count") or 0) >= threshold:
        trip_global(reason=reason or str(http_status))


def trip_global(*, reason: str = "api_blocked") -> None:
    data = _load_state()
    data["global_trip"] = {
        "at": datetime.now(timezone.utc).isoformat(),
        "reason": reason[:120],
        "until_hours": _block_ttl_hours(),
    }
    _save_state(data)
    _log_once("global_trip", f"[Racing API] global pause ({reason}) — scrape-first active")


def global_trip_active() -> bool:
    data = _load_state()
    trip = data.get("global_trip")
    if not isinstance(trip, dict) or not trip.get("at"):
        return False
    forbidden = data.get("forbidden")
    if isinstance(forbidden, dict) and forbidden.get("at"):
        return True
    return bool(trip.get("at"))


def racing_api_traffic_allowed() -> bool:
    if os.getenv("HIBS_SKIP_RACING_API", "").strip().lower() in ("1", "true", "yes", "on"):
        return False
    if global_trip_active():
        return False
    from hibs_racing.scrape_first import racing_api_configured

    if not racing_api_configured():
        return False
    return True


def status_payload() -> Dict[str, Any]:
    from hibs_racing.scrape_first import racing_api_configured, scrape_first_mode

    data = _load_state()
    return {
        "traffic_allowed": racing_api_traffic_allowed(),
        "scrape_first": scrape_first_mode(),
        "api_configured": racing_api_configured(),
        "global_trip": global_trip_active(),
        "forbidden": data.get("forbidden"),
        "failure_count": data.get("failure_count", 0),
        "fallback_source": (os.getenv("HIBS_RACING_SCRAPE_SOURCE") or "rpscrape").strip(),
    }


def _log_once(key: str, message: str) -> None:
    with _log_once_lock:
        if key in _logged_once:
            return
        _logged_once.add(key)
    print(message)
