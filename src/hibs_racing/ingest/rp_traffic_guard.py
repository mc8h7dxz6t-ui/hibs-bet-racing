"""Racing Post shared traffic guard — one credential pool, many consumers.

All live RP traffic (rpscrape results, racecards, verdicts, dual-source enrich)
shares EMAIL + ACCESS_TOKEN. This module coordinates concurrency and trips
after rate-limit signals so refresh + thin rescue + CLI scrape do not compound.
"""

from __future__ import annotations

import fcntl
import json
import os
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, Optional

_log_once_lock = threading.Lock()
_logged_once: set[str] = set()

_inproc_sem: Optional[threading.BoundedSemaphore] = None


def _cache_dir() -> Path:
    return Path(os.getenv("HIBS_RACING_CACHE_DIR", "data/.cache"))


def _state_path() -> Path:
    return _cache_dir() / "rp_traffic_guard_v1.json"


def _lock_path() -> Path:
    return _cache_dir() / "rp_traffic_guard_v1.lock"


def _trip_ttl_hours() -> float:
    try:
        return max(0.25, float(os.getenv("HIBS_RP_TRIP_TTL_HOURS", "1")))
    except ValueError:
        return 1.0


def _max_concurrent_live() -> int:
    try:
        return max(1, int(os.getenv("HIBS_RP_MAX_CONCURRENT_LIVE", "1")))
    except ValueError:
        return 1


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


def record_rate_limit(*, reason: str = "rate_limit", http_status: int | None = None) -> None:
    data = _load_state()
    data["trip"] = {
        "at": datetime.now(timezone.utc).isoformat(),
        "reason": (reason or "")[:160],
        "status": http_status,
        "ttl_hours": _trip_ttl_hours(),
    }
    data["failure_count"] = int(data.get("failure_count") or 0) + 1
    _save_state(data)
    _log_once(
        "rp_trip",
        f"[Racing Post] rate-limit trip ({reason}) — cache-only for {_trip_ttl_hours():.1f}h",
    )


def rp_live_traffic_allowed() -> bool:
    if os.getenv("HIBS_SKIP_RP_LIVE", "").strip().lower() in ("1", "true", "yes", "on"):
        return False
    if global_trip_active():
        return False
    from hibs_racing.ingest.racecards import rp_auth_configured

    if not rp_auth_configured():
        return False
    return True


def status_payload() -> Dict[str, Any]:
    from hibs_racing.ingest.racecards import rp_auth_configured

    data = _load_state()
    return {
        "live_allowed": rp_live_traffic_allowed(),
        "auth_configured": rp_auth_configured(),
        "global_trip": global_trip_active(),
        "trip": data.get("trip"),
        "failure_count": int(data.get("failure_count") or 0),
        "max_concurrent_live": _max_concurrent_live(),
        "trip_ttl_hours": _trip_ttl_hours(),
        "shared_pool": "EMAIL+ACCESS_TOKEN",
        "consumers": [
            "ingest.scrape (rpscrape results)",
            "ingest.racecards (live racecards)",
            "cards.enrich (dual_source_enrich)",
            "ingest.rp_verdict",
            "scrapers.field_resolver (thin rescue)",
        ],
    }


def _inproc_semaphore() -> threading.BoundedSemaphore:
    global _inproc_sem
    if _inproc_sem is None:
        _inproc_sem = threading.BoundedSemaphore(_max_concurrent_live())
    return _inproc_sem


@contextmanager
def acquire_rp_live_slot(*, label: str = "rp_live") -> Iterator[None]:
    """Cross-process slot for live RP subprocess/API (max HIBS_RP_MAX_CONCURRENT_LIVE)."""
    if not rp_live_traffic_allowed():
        raise RuntimeError("rp_live_traffic_blocked")
    sem = _inproc_semaphore()
    acquired = sem.acquire(timeout=max(1.0, float(os.getenv("HIBS_RP_SLOT_WAIT_SEC", "30"))))
    if not acquired:
        record_rate_limit(reason=f"slot_timeout:{label}")
        raise RuntimeError("rp_live_slot_timeout")
    lock_fd = None
    try:
        _lock_path().parent.mkdir(parents=True, exist_ok=True)
        lock_fd = open(_lock_path(), "a+", encoding="utf-8")
        fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        if lock_fd is not None:
            try:
                fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
                lock_fd.close()
            except OSError:
                pass
        sem.release()


def polite_rp_pause(key: str = "rp_scrape_day_pause_sec") -> None:
    from hibs_racing.ingest.rate_limit import polite_sleep

    polite_sleep(key)


def _log_once(key: str, message: str) -> None:
    with _log_once_lock:
        if key in _logged_once:
            return
        _logged_once.add(key)
    print(message)
