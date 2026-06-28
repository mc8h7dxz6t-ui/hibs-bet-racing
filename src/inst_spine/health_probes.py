"""Shared /health and /ready probe helpers for HTTP serves."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any


def sqlite_db_ready(path: str | Path, *, probe_table: str | None = None) -> tuple[bool, str]:
    """Return (ok, detail) after a lightweight SQLite connectivity check."""
    db = Path(path)
    if not db.parent.exists():
        try:
            db.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return False, f"mkdir_failed:{exc}"
    try:
        with sqlite3.connect(db, timeout=5.0) as conn:
            if probe_table:
                row = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                    (probe_table,),
                ).fetchone()
                if row is None:
                    return True, "db_open_no_table_yet"
            conn.execute("SELECT 1")
        return True, "sqlite_ok"
    except sqlite3.Error as exc:
        return False, f"sqlite_error:{exc}"


def redis_ready_from_env(*, env_var: str = "INST_REDIS_URL") -> tuple[bool, str]:
    """Optional Redis probe when URL is configured."""
    url = os.getenv(env_var, "").strip()
    if not url:
        return True, "redis_not_configured"
    try:
        import redis

        client = redis.from_url(url, decode_responses=True, socket_connect_timeout=2)
        try:
            if client.ping():
                return True, "redis_ok"
            return False, "redis_ping_failed"
        finally:
            client.close()
    except Exception as exc:
        return False, f"redis_error:{exc}"


def readiness_payload(
    *,
    product: str,
    checks: dict[str, tuple[bool, str]],
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Standard JSON body for GET /ready — 503 when any required check fails."""
    details = {name: {"ok": ok, "detail": detail} for name, (ok, detail) in checks.items()}
    ready = all(ok for ok, _ in checks.values())
    body: dict[str, Any] = {
        "ok": ready,
        "ready": ready,
        "product": product,
        "checks": details,
    }
    if extra:
        body.update(extra)
    return body
