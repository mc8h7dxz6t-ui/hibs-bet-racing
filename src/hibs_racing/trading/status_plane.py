"""Supervised trading daemon heartbeat — eliminates web split-brain."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from hibs_racing.trading.runtime_paths import ensure_runtime_dir, racing_runtime_dir, trading_status_path


def status_path() -> Path:
    return trading_status_path()


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _atomic_write_json(path: Path, body: Dict[str, Any]) -> None:
    ensure_runtime_dir()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f"{path.suffix}.tmp")
    tmp.write_text(json.dumps(body, default=str), encoding="utf-8")
    tmp.replace(path)


def _heartbeat_write_paths() -> list[Path]:
    primary = status_path()
    paths = [primary]
    disk = racing_runtime_dir() / "trading_daemon.json"
    if disk != primary:
        paths.append(disk)
    return paths


def write_heartbeat(*, payload: Dict[str, Any]) -> None:
    body = {
        "updated_at": _utc_now(),
        "ts": time.time(),
        **payload,
    }
    last_exc: OSError | None = None
    for path in _heartbeat_write_paths():
        try:
            _atomic_write_json(path, body)
            return
        except OSError as exc:
            last_exc = exc
            continue
    if last_exc is not None:
        raise last_exc


def read_status(*, max_age_sec: float = 30.0) -> Dict[str, Any]:
    seen: set[str] = set()
    for path in _heartbeat_write_paths():
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return {"ok": False, "active": False, "error": str(exc)[:120], "path": str(path)}
        age = time.time() - float(data.get("ts") or 0)
        active = age <= max_age_sec
        return {
            "ok": active,
            "active": active,
            "age_sec": round(age, 2),
            "path": str(path),
            **data,
        }
    return {
        "ok": False,
        "active": False,
        "error": "status_file_missing",
        "path": str(status_path()),
    }


def daemon_active(*, max_age_sec: float = 30.0) -> bool:
    return bool(read_status(max_age_sec=max_age_sec).get("active"))
