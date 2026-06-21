"""Football-Data.org 403/forbidden guard — stop hammering paid-tier competitions on free keys."""

from __future__ import annotations

import os
import threading
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Set

_log_once_lock = threading.Lock()
_logged_once: Set[str] = set()


def _cache():
    from hibs_predictor.cache import Cache

    return Cache()


def _blocklist_key() -> str:
    return "football_data_org_forbidden_comps_v1"


def _global_trip_key() -> str:
    return "football_data_org_global_forbidden_v1"


def _block_ttl_hours() -> float:
    try:
        return max(1.0, float(os.getenv("HIBS_FOOTBALL_DATA_FORBIDDEN_TTL_HOURS", "24")))
    except ValueError:
        return 24.0


def block_ttl_hours() -> float:
    return _block_ttl_hours()


def _skip_comps_env() -> Set[str]:
    raw = (os.getenv("HIBS_FOOTBALL_DATA_SKIP_COMPS") or "").strip()
    if not raw:
        return set()
    return {c.strip().upper() for c in raw.split(",") if c.strip()}


def _paid_tier_comps_default() -> Set[str]:
    """Competitions that typically 403 on Football-Data.org free tier."""
    raw = (os.getenv("HIBS_FOOTBALL_DATA_PAID_COMPS") or "WC,CL,EL,UECL,CDR,DFB,SA,FL1,BL1").strip()
    return {c.strip().upper() for c in raw.split(",") if c.strip()}


def _auto_skip_paid_comps() -> bool:
    return os.getenv("HIBS_FOOTBALL_DATA_AUTO_SKIP_PAID", "1").strip().lower() in ("1", "true", "yes", "on")


def _load_blocklist() -> Dict[str, Any]:
    hit = _cache().peek(_blocklist_key())
    return dict(hit) if isinstance(hit, dict) else {}


def _save_blocklist(data: Dict[str, Any]) -> None:
    _cache().set(_blocklist_key(), data, ttl_hours=_block_ttl_hours())


def competition_from_endpoint(endpoint: str) -> Optional[str]:
    ep = (endpoint or "").strip().strip("/")
    parts = ep.split("/")
    if len(parts) >= 2 and parts[0] == "competitions":
        return parts[1].upper()
    return None


def record_forbidden(competition_code: str, *, http_status: int = 403, reason: str = "") -> None:
    comp = (competition_code or "").strip().upper()
    if not comp:
        return
    data = _load_blocklist()
    data[comp] = {
        "at": datetime.now(timezone.utc).isoformat(),
        "status": http_status,
        "reason": (reason or "")[:120],
    }
    _save_blocklist(data)
    _log_once(f"forbidden:{comp}", f"[Football-Data.org] competition {comp} blocked ({http_status}) — scrape fallback for 24h")

    failures = sum(1 for v in data.values() if isinstance(v, dict))
    threshold = 3
    try:
        threshold = max(1, int(os.getenv("HIBS_FOOTBALL_DATA_GLOBAL_TRIP_AFTER", "3")))
    except ValueError:
        pass
    if failures >= threshold:
        trip_global_forbidden(reason=f"{failures} competitions forbidden")


def trip_global_forbidden(*, reason: str = "403") -> None:
    """Pause all Football-Data.org calls until TTL expires."""
    from hibs_predictor.api_clients import football_data_trip_minute_guard

    ttl_h = _block_ttl_hours()
    _cache().set(
        _global_trip_key(),
        {"at": datetime.now(timezone.utc).isoformat(), "reason": reason[:120]},
        ttl_hours=ttl_h,
    )
    football_data_trip_minute_guard()
    _log_once("global_trip", f"[Football-Data.org] global pause ({reason}) — use FotMob/ESPN/scrapers")


def global_forbidden_active() -> bool:
    hit = _cache().peek(_global_trip_key())
    return isinstance(hit, dict) and bool(hit.get("at"))


def competition_allowed(competition_code: Optional[str]) -> bool:
    comp = (competition_code or "").strip().upper()
    if not comp:
        return True
    if comp in _skip_comps_env():
        return False
    if _auto_skip_paid_comps() and comp in _paid_tier_comps_default():
        blocked = _load_blocklist()
        if comp not in blocked:
            record_forbidden(comp, http_status=403, reason="paid_tier_auto_skip")
        return False
    blocked = _load_blocklist()
    if comp in blocked:
        return False
    return True


def football_data_traffic_allowed(competition_code: Optional[str] = None) -> bool:
    from hibs_predictor.api_clients import football_data_requests_allowed

    if not football_data_requests_allowed():
        return False
    if global_forbidden_active():
        return False
    if competition_code and not competition_allowed(competition_code):
        return False
    return True


def status_payload() -> Dict[str, Any]:
    blocked = _load_blocklist()
    return {
        "global_forbidden": global_forbidden_active(),
        "blocked_competitions": list(blocked.keys()),
        "blocked_count": len(blocked),
        "auto_skip_paid": _auto_skip_paid_comps(),
        "skip_comps_env": sorted(_skip_comps_env()),
    }


def _log_once(key: str, message: str) -> None:
    with _log_once_lock:
        if key in _logged_once:
            return
        _logged_once.add(key)
    print(message)
