"""Resolve data paths relative to the hibs-bet app root."""

from __future__ import annotations

import os
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]


def app_root() -> Path:
    explicit = (os.getenv("DEPLOY_PATH") or os.getenv("HIBS_APP_ROOT") or "").strip()
    if explicit:
        return Path(explicit)
    return _REPO_ROOT


def resolve_data_path(env_var: str, default_rel: str) -> Path:
    """Return absolute path from env override or default under app root."""
    raw = (os.getenv(env_var) or "").strip()
    if raw:
        p = Path(raw)
        return p if p.is_absolute() else app_root() / p
    return app_root() / default_rel
