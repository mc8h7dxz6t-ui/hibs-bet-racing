"""Permit store — authorize-before-invoke semantics (like spend holds)."""

from __future__ import annotations

import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


@dataclass
class PermitRecord:
    permit_id: str
    agent_id: str
    tool_name: str
    decision: str
    status: str
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "permit_id": self.permit_id,
            "agent_id": self.agent_id,
            "tool_name": self.tool_name,
            "decision": self.decision,
            "status": self.status,
            "reason": self.reason,
        }


_SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_permits (
    permit_id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    decision TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    reason TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT '',
    expires_at TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_agent_permits_agent ON agent_permits(agent_id, status);
"""


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _default_ttl_seconds() -> int:
    import os

    return int(os.getenv("AGENT_LEDGER_PERMIT_TTL_SECONDS", "3600"))


class PermitStore:
    """SQLite-backed open permits — complete attestation chains to authorize row."""

    def __init__(self, database: Path) -> None:
        self.database = Path(database)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
            cols = {row[1] for row in conn.execute("PRAGMA table_info(agent_permits)")}
            if "expires_at" not in cols:
                conn.execute(
                    "ALTER TABLE agent_permits ADD COLUMN expires_at TEXT NOT NULL DEFAULT ''"
                )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.database, timeout=30.0, isolation_level=None)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def create_permit(
        self,
        *,
        agent_id: str,
        tool_name: str,
        decision: str,
        reason: str,
        permit_id: str | None = None,
    ) -> PermitRecord:
        pid = permit_id or str(uuid.uuid4())
        created = _utc_now()
        ttl = _default_ttl_seconds()
        expires = (datetime.now(timezone.utc) + timedelta(seconds=ttl)).strftime("%Y-%m-%dT%H:%M:%SZ")
        with self._lock:
            with self._connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                existing = conn.execute(
                    "SELECT permit_id FROM agent_permits WHERE permit_id = ?",
                    (pid,),
                ).fetchone()
                if existing:
                    conn.execute("ROLLBACK")
                    raise ValueError(f"duplicate_permit_id:{pid}")
                status = "open" if decision == "permit" else "closed"
                conn.execute(
                    "INSERT INTO agent_permits "
                    "(permit_id, agent_id, tool_name, decision, status, reason, created_at, expires_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (pid, agent_id, tool_name, decision, status, reason, created, expires),
                )
                conn.execute("COMMIT")
        return PermitRecord(
            permit_id=pid,
            agent_id=agent_id,
            tool_name=tool_name,
            decision=decision,
            status=status,
            reason=reason,
        )

    def _is_expired(self, expires_at: str) -> bool:
        if not expires_at:
            return False
        try:
            exp = datetime.strptime(expires_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        except ValueError:
            return False
        return datetime.now(timezone.utc) >= exp

    def sweep_expired(self) -> int:
        """Mark open permits past TTL as expired — returns count swept."""
        now = _utc_now()
        with self._lock:
            with self._connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                rows = conn.execute(
                    "SELECT permit_id, expires_at FROM agent_permits WHERE status = 'open'"
                ).fetchall()
                swept = 0
                for permit_id, expires_at in rows:
                    if self._is_expired(expires_at or ""):
                        conn.execute(
                            "UPDATE agent_permits SET status = 'expired' WHERE permit_id = ?",
                            (permit_id,),
                        )
                        swept += 1
                conn.execute("COMMIT")
        return swept

    def get(self, permit_id: str) -> PermitRecord | None:
        self.sweep_expired()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT permit_id, agent_id, tool_name, decision, status, reason "
                "FROM agent_permits WHERE permit_id = ?",
                (permit_id,),
            ).fetchone()
        if not row:
            return None
        return PermitRecord(
            permit_id=row[0],
            agent_id=row[1],
            tool_name=row[2],
            decision=row[3],
            status=row[4],
            reason=row[5] or "",
        )

    def complete(self, permit_id: str) -> tuple[bool, str]:
        self.sweep_expired()
        with self._lock:
            with self._connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute(
                    "SELECT decision, status, expires_at FROM agent_permits WHERE permit_id = ?",
                    (permit_id,),
                ).fetchone()
                if not row:
                    conn.execute("ROLLBACK")
                    return False, "permit_not_found"
                decision, status, expires_at = row[0], row[1], row[2]
                if self._is_expired(expires_at or ""):
                    conn.execute(
                        "UPDATE agent_permits SET status = 'expired' WHERE permit_id = ?",
                        (permit_id,),
                    )
                    conn.execute("COMMIT")
                    return False, "permit_expired"
                if decision != "permit":
                    conn.execute("ROLLBACK")
                    return False, f"not_permitted:{decision}"
                if status != "open":
                    conn.execute("ROLLBACK")
                    return False, f"permit_status:{status}"
                conn.execute(
                    "UPDATE agent_permits SET status = 'completed' WHERE permit_id = ?",
                    (permit_id,),
                )
                conn.execute("COMMIT")
        return True, "completed"

    def count_open(self) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM agent_permits WHERE status = 'open'"
            ).fetchone()
        return int(row[0]) if row else 0
