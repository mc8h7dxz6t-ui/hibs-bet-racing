"""Append-only ledger with Lamport ordering and async write-behind."""

from __future__ import annotations

import json
import sqlite3
import threading
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from inst_spine.clocks import LamportClock, utc_now_iso
from inst_spine.contracts import LedgerEntry, stable_id
from inst_spine.hash import GENESIS_HASH, chain_hash, verify_chain, verify_lamport_monotonic

_SCHEMA = """
CREATE TABLE IF NOT EXISTS inst_ledger (
    entry_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    writer_id TEXT NOT NULL,
    lamport_seq INTEGER NOT NULL,
    wall_time_utc TEXT NOT NULL,
    manifest_id TEXT,
    payload_json TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    prev_hash TEXT NOT NULL,
    entry_hash TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_inst_ledger_lamport ON inst_ledger(writer_id, lamport_seq);
"""


@dataclass
class _PendingWrite:
    event_type: str
    writer_id: str
    lamport_seq: int
    wall_time_utc: str
    manifest_id: str | None
    payload: dict[str, Any]
    metadata: dict[str, Any]
    prev_hash: str
    entry_hash: str
    entry_id: str


class AppendOnlyLedger:
    """SQLite ledger with optional background write-behind queue."""

    def __init__(
        self,
        database: Path,
        *,
        writer_id: str = "default",
        async_writes: bool = False,
        max_queue: int = 10_000,
    ) -> None:
        self.database = Path(database)
        self.writer_id = writer_id
        self.clock = LamportClock(writer_id)
        self._async = async_writes
        self._queue: deque[_PendingWrite] = deque()
        self._lock = threading.Lock()
        self._last_hash = GENESIS_HASH
        self._max_queue = max_queue
        self._worker: threading.Thread | None = None
        self._stop = threading.Event()
        self._init_db()
        self._load_tail_hash()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.database, timeout=30.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        return conn

    def _init_db(self) -> None:
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
            conn.commit()

    def _load_tail_hash(self) -> None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT entry_hash, lamport_seq FROM inst_ledger ORDER BY lamport_seq DESC LIMIT 1"
            ).fetchone()
        if row:
            self._last_hash = str(row[0])
            self.clock.observe(int(row[1]))

    def start_async_writer(self) -> None:
        if not self._async or (self._worker and self._worker.is_alive()):
            return

        def _run() -> None:
            while not self._stop.is_set():
                item: _PendingWrite | None = None
                with self._lock:
                    if self._queue:
                        item = self._queue.popleft()
                if item is None:
                    self._stop.wait(0.05)
                    continue
                self._persist(item)

        self._worker = threading.Thread(target=_run, name="inst-ledger-writer", daemon=True)
        self._worker.start()

    def stop_async_writer(self, *, flush: bool = True) -> None:
        if flush:
            self.flush()
        self._stop.set()
        if self._worker:
            self._worker.join(timeout=5.0)

    def flush(self) -> int:
        flushed = 0
        while True:
            with self._lock:
                if not self._queue:
                    break
                item = self._queue.popleft()
            self._persist(item)
            flushed += 1
        return flushed

    def append(
        self,
        *,
        event_type: str,
        payload: dict[str, Any],
        manifest_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> LedgerEntry:
        lamport = self.clock.tick()
        wall = utc_now_iso()
        meta = metadata or {}
        prev = self._last_hash
        entry_hash = chain_hash(
            payload=payload,
            prev_hash=prev,
            lamport_seq=lamport,
            metadata=meta,
        )
        entry_id = stable_id(event_type, self.writer_id, str(lamport), entry_hash[:16])
        pending = _PendingWrite(
            event_type=event_type,
            writer_id=self.writer_id,
            lamport_seq=lamport,
            wall_time_utc=wall,
            manifest_id=manifest_id,
            payload=payload,
            metadata=meta,
            prev_hash=prev,
            entry_hash=entry_hash,
            entry_id=entry_id,
        )
        self._last_hash = entry_hash

        if self._async:
            with self._lock:
                if len(self._queue) >= self._max_queue:
                    raise RuntimeError("ledger write-behind queue full")
                self._queue.append(pending)
        else:
            self._persist(pending)

        return LedgerEntry(
            entry_id=entry_id,
            event_type=event_type,
            writer_id=self.writer_id,
            lamport_seq=lamport,
            wall_time_utc=wall,
            manifest_id=manifest_id,
            payload=payload,
            prev_hash=prev,
            entry_hash=entry_hash,
        )

    def _persist(self, item: _PendingWrite) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO inst_ledger (
                    entry_id, event_type, writer_id, lamport_seq, wall_time_utc,
                    manifest_id, payload_json, metadata_json, prev_hash, entry_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.entry_id,
                    item.event_type,
                    item.writer_id,
                    item.lamport_seq,
                    item.wall_time_utc,
                    item.manifest_id,
                    json.dumps(item.payload, sort_keys=True, default=str),
                    json.dumps(item.metadata, sort_keys=True, default=str),
                    item.prev_hash,
                    item.entry_hash,
                ),
            )
            conn.commit()

    def list_entries(self, *, limit: int = 1000) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT entry_id, event_type, writer_id, lamport_seq, wall_time_utc,
                       manifest_id, payload_json, metadata_json, prev_hash, entry_hash
                FROM inst_ledger ORDER BY lamport_seq ASC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            out.append(
                {
                    "entry_id": row[0],
                    "event_type": row[1],
                    "writer_id": row[2],
                    "lamport_seq": row[3],
                    "wall_time_utc": row[4],
                    "manifest_id": row[5],
                    "payload": json.loads(row[6]),
                    "metadata": json.loads(row[7]),
                    "prev_hash": row[8],
                    "entry_hash": row[9],
                }
            )
        return out

    def verify(self) -> dict[str, Any]:
        entries = self.list_entries()
        chain = verify_chain(entries)
        lamport_ok = verify_lamport_monotonic(entries)
        return {
            "chain_ok": chain.ok,
            "chain_message": chain.message,
            "entries_checked": chain.entries_checked,
            "first_mismatch_index": chain.first_mismatch_index,
            "lamport_monotonic": lamport_ok,
        }


def memory_idempotency_store() -> dict[str, float]:
    """Hot-path idempotency bitmap substitute for Proxy-Risk."""
    return {}


class IdempotencyGuard:
    """In-memory duplicate request blocker with TTL."""

    def __init__(self, *, ttl_sec: float = 300.0) -> None:
        self.ttl_sec = ttl_sec
        self._seen: dict[str, float] = {}
        self._lock = threading.Lock()

    def check_and_set(self, key: str, *, now: float | None = None) -> bool:
        """Return True if new; False if duplicate within TTL."""
        from inst_spine.clocks import monotonic_seconds

        now = now if now is not None else monotonic_seconds()
        with self._lock:
            self._purge(now)
            if key in self._seen:
                return False
            self._seen[key] = now
            return True

    def _purge(self, now: float) -> None:
        expired = [k for k, ts in self._seen.items() if now - ts > self.ttl_sec]
        for k in expired:
            del self._seen[k]
