"""Supervised trading daemon heartbeat — eliminates web split-brain."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

_DEFAULT_PATH = Path("/var/run/hibs/trading_daemon.json")


def status_path() -> Path:
    raw = (os.getenv("HIBS_TRADING_STATUS_FILE") or str(_DEFAULT_PATH)).strip()
    return Path(raw)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_heartbeat(*, payload: Dict[str, Any]) -> None:
    path = status_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {
        "updated_at": _utc_now(),
        "ts": time.time(),
        **payload,
    }
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(body, default=str), encoding="utf-8")
    tmp.replace(path)


def read_status(*, max_age_sec: float = 30.0) -> Dict[str, Any]:
    path = status_path()
    if not path.is_file():
        return {"ok": False, "active": False, "error": "status_file_missing", "path": str(path)}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "active": False, "error": str(exc)[:120]}
    age = time.time() - float(data.get("ts") or 0)
    active = age <= max_age_sec
    return {
        "ok": active,
        "active": active,
        "age_sec": round(age, 2),
        **data,
    }


def daemon_active(*, max_age_sec: float = 30.0) -> bool:
    return bool(read_status(max_age_sec=max_age_sec).get("active"))
