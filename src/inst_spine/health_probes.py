"""Shared /health and /ready probe helpers for HTTP serves."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any

from inst_spine.ledger_factory import is_postgres_dsn, open_ledger


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


def ledger_chain_ready(database: str | Path) -> tuple[bool, str]:
    """Verify append-only chain when ledger exists (SQLite or Postgres DSN)."""
    dsn_or_path = str(database)
    if is_postgres_dsn(dsn_or_path):
        try:
            verify = open_ledger(dsn_or_path).verify()
        except Exception as exc:
            return False, f"ledger_open_error:{exc}"
        if not verify.get("chain_ok"):
            return False, f"chain_broken:{verify}"
        return True, "chain_ok"
    path = Path(database)
    if not path.exists():
        return True, "ledger_not_initialized"
    try:
        verify = open_ledger(path).verify()
    except Exception as exc:
        return False, f"ledger_open_error:{exc}"
    if not verify.get("chain_ok"):
        return False, f"chain_broken:{verify}"
    return True, "chain_ok"


def wallet_state_ready(database: str | Path) -> tuple[bool, str]:
    """Spend wallet connectivity — balance readable, not locked-out on probe failure."""
    try:
        from spend_guard.wallet_factory import open_wallet

        wallet = open_wallet(database)
        state = wallet.get_state()
        if state.locked:
            return True, "wallet_locked_operational"
        return True, f"balance={state.balance}"
    except Exception as exc:
        return False, f"wallet_error:{exc}"


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
