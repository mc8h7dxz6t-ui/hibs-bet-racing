"""Per-runner liquidity router disarm registry — fail-closed capital shield."""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

_LOCK = threading.Lock()
_DISARMED: dict[str, str] = {}


def _disarm_file() -> Path:
    raw = os.environ.get("HIBS_RUNNER_DISARM_FILE", "").strip()
    if raw:
        return Path(raw)
    return Path("/var/run/hibs/drift_disarmed_runners.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_file() -> dict[str, str]:
    disarm_file = _disarm_file()
    if not disarm_file.exists():
        return {}
    try:
        data = json.loads(disarm_file.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items()}
    except (OSError, json.JSONDecodeError, TypeError):
        return {}
    return {}


def _persist_file() -> None:
    try:
        disarm_file = _disarm_file()
        disarm_file.parent.mkdir(parents=True, exist_ok=True)
        disarm_file.write_text(json.dumps(_DISARMED, indent=2), encoding="utf-8")
    except OSError:
        pass


def disarm_runner(runner_id: str, *, reason: str = "drift_gate") -> None:
    rid = str(runner_id).strip()
    if not rid:
        return
    with _LOCK:
        _DISARMED[rid] = f"{_utc_now()}:{reason}"
        _persist_file()


def is_disarmed(runner_id: str) -> bool:
    rid = str(runner_id).strip()
    if not rid:
        return False
    with _LOCK:
        if rid in _DISARMED:
            return True
        file_state = _load_file()
        if rid in file_state:
            _DISARMED[rid] = file_state[rid]
            return True
    return False


def armed_runners_filter(runner_ids: list[str]) -> list[str]:
    return [rid for rid in runner_ids if not is_disarmed(rid)]


def disarmed_snapshot() -> dict[str, str]:
    with _LOCK:
        merged = dict(_load_file())
        merged.update(_DISARMED)
        return merged
