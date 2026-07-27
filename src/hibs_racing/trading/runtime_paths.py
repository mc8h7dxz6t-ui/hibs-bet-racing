"""Writable runtime paths for trading daemon (avoids /var/run/hibs when PrivateTmp blocks host FS)."""

from __future__ import annotations

import os
from pathlib import Path


def racing_deploy_root() -> Path:
    return Path(os.getenv("HIBS_RACING_DEPLOY_PATH", "/opt/hibs-racing"))


def racing_runtime_dir() -> Path:
    raw = (os.getenv("HIBS_RACING_RUNTIME_DIR") or "").strip()
    if raw:
        return Path(raw)
    return racing_deploy_root() / "run"


def trading_status_path() -> Path:
    raw = (os.getenv("HIBS_TRADING_STATUS_FILE") or "").strip()
    if raw:
        return Path(raw)
    return racing_runtime_dir() / "trading_daemon.json"


def runner_disarm_path() -> Path:
    raw = (os.getenv("HIBS_RUNNER_DISARM_FILE") or "").strip()
    if raw:
        return Path(raw)
    return racing_runtime_dir() / "drift_disarmed_runners.json"


def ensure_runtime_dir() -> Path:
    path = racing_runtime_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path
