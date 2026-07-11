"""Append-only ledger — sync WAL + async SQLite write-behind."""

from __future__ import annotations

import json
import sqlite3
import threading
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from inst_spine.clocks import LamportClock, utc_now_iso
from inst_spine.contracts import LedgerEntry, stable_id
from inst_spine.hash import (
    GENESIS_EVENT,
    GENESIS_LAMPORT,
    build_genesis_record,
    chain_hash,
    new_instance_uuid,
    read_genesis_anchor,
    verify_chain,
    verify_genesis_block,
    verify_lamport_monotonic,
    write_genesis_anchor,
)
from inst_spine.wal import AppendOnlyWal

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
CREATE INDEX IF NOT EXISTS idx_inst_ledger_event_type ON inst_ledger(event_type);
CREATE TABLE IF NOT EXISTS inst_ledger_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
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
    """
    Durability model:
      1. SYNC: append to flat WAL (fsync) — survives crash before SQLite flush
      2. ASYNC: SQLite indexing via write-behind worker (optional)
    """

    def __init__(
        self,
        database: Path,
        *,
        writer_id: str = "default",
        config_hash: str | None = None,
        async_writes: bool = False,
        max_queue: int = 10_000,
    ) -> None:
        self.database = Path(database)
        self.writer_id = writer_id
        self.config_hash = config_hash or stable_id(writer_id, "config", "v1")
        self.wal_path = self.database.with_suffix(".wal")
        self.anchor_path = self.database.with_suffix(".genesis.json")
        self.wal = AppendOnlyWal(self.wal_path)
        self.clock = LamportClock(writer_id)
        self._async = async_writes
        self._queue: deque[_PendingWrite] = deque()
        self._lock = threading.Lock()
        self._last_hash = ""
        self._max_queue = max_queue
        self._worker: threading.Thread | None = None
        self._stop = threading.Event()
        self._instance_uuid = ""
        self._init_db()
        self._ensure_genesis()
        self._replay_wal_to_sqlite()
        self._load_tail_state()

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

    def _ensure_genesis(self) -> None:
        wal_records = self.wal.read_all()
        genesis_wal = next((r for r in wal_records if r.get("event_type") == GENESIS_EVENT), None)
        if genesis_wal:
            self._instance_uuid = str((genesis_wal.get("payload") or {}).get("instance_uuid") or "")
            self._last_hash = str(genesis_wal.get("entry_hash") or "")
            return

        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload_json, entry_hash FROM inst_ledger WHERE event_type = ? LIMIT 1",
                (GENESIS_EVENT,),
            ).fetchone()
        if row:
            payload = json.loads(row[0])
            self._instance_uuid = str(payload.get("instance_uuid") or "")
            self._last_hash = str(row[1])
            return

        instance_uuid = new_instance_uuid()
        wall = utc_now_iso()
        genesis = build_genesis_record(
            instance_uuid=instance_uuid,
            config_hash=self.config_hash,
            writer_id=self.writer_id,
            wall_time_utc=wall,
        )
        self._instance_uuid = instance_uuid
        self._last_hash = genesis["entry_hash"]
        self.wal.append(genesis)
        write_genesis_anchor(
            self.anchor_path,
            instance_uuid=instance_uuid,
            genesis_hash=genesis["entry_hash"],
            config_hash=self.config_hash,
        )
        self._persist_record(genesis)

    def _replay_wal_to_sqlite(self) -> None:
        existing = self._sqlite_entry_ids()
        for record in self.wal.read_all():
            eid = str(record.get("entry_id") or "")
            if eid and eid not in existing:
                self._persist_record(record)

    def _sqlite_entry_ids(self) -> set[str]:
        with self._connect() as conn:
            rows = conn.execute("SELECT entry_id FROM inst_ledger").fetchall()
        return {str(r[0]) for r in rows}

    def _load_tail_state(self) -> None:
        tail = self.wal.tail_hash()
        if tail:
            self._last_hash = tail
        records = self.wal.read_all()
        for rec in reversed(records):
            if rec.get("event_type") != GENESIS_EVENT:
                self.clock.observe(int(rec.get("lamport_seq") or GENESIS_LAMPORT))
                break

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
            self._worker = None

    def close(self) -> None:
        """Stop background workers — call in tests and long-lived servers."""
        self.stop_async_writer(flush=True)

    def __enter__(self) -> AppendOnlyLedger:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

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
        if event_type == GENESIS_EVENT:
            raise ValueError("genesis block is immutable — cannot append manually")

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
        record = {
            "entry_id": entry_id,
            "event_type": event_type,
            "writer_id": self.writer_id,
            "lamport_seq": lamport,
            "wall_time_utc": wall,
            "manifest_id": manifest_id,
            "payload": payload,
            "metadata": meta,
            "prev_hash": prev,
            "entry_hash": entry_hash,
        }

        # SYNC path — WAL fsync before returning (crash-safe H_n state)
        self.wal.append(record)
        self._last_hash = entry_hash

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
        self._persist_record(
            {
                "entry_id": item.entry_id,
                "event_type": item.event_type,
                "writer_id": item.writer_id,
                "lamport_seq": item.lamport_seq,
                "wall_time_utc": item.wall_time_utc,
                "manifest_id": item.manifest_id,
                "payload": item.payload,
                "metadata": item.metadata,
                "prev_hash": item.prev_hash,
                "entry_hash": item.entry_hash,
            }
        )

    def _persist_record(self, record: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO inst_ledger (
                    entry_id, event_type, writer_id, lamport_seq, wall_time_utc,
                    manifest_id, payload_json, metadata_json, prev_hash, entry_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["entry_id"],
                    record["event_type"],
                    record["writer_id"],
                    record["lamport_seq"],
                    record["wall_time_utc"],
                    record.get("manifest_id"),
                    json.dumps(record.get("payload") or {}, sort_keys=True, default=str),
                    json.dumps(record.get("metadata") or {}, sort_keys=True, default=str),
                    record["prev_hash"],
                    record["entry_hash"],
                ),
            )
            conn.commit()

    def list_entries(self, *, limit: int = 10000) -> list[dict[str, Any]]:
        """Authoritative order from WAL tail (survives SQLite lag)."""
        return self.wal.read_tail(limit=limit)

    def verify(self) -> dict[str, Any]:
        entries = self.list_entries()
        anchor = read_genesis_anchor(self.anchor_path)
        genesis_row = entries[0] if entries else None
        genesis = verify_genesis_block(genesis_row, anchor=anchor)
        chain = verify_chain(entries, anchor=anchor, require_genesis=True)
        lamport_ok = verify_lamport_monotonic(entries)
        wal_sqlite_gap = self.wal.count() - len(self._sqlite_entry_ids())
        return {
            "chain_ok": chain.ok and genesis.ok,
            "chain_message": chain.message if chain.ok else (genesis.message if not genesis.ok else chain.message),
            "genesis_ok": genesis.ok,
            "genesis_message": genesis.message,
            "entries_checked": chain.entries_checked,
            "first_mismatch_index": chain.first_mismatch_index,
            "lamport_monotonic": lamport_ok,
            "wal_records": self.wal.count(),
            "wal_sqlite_pending": max(0, wal_sqlite_gap),
            "instance_uuid": self._instance_uuid,
        }


class IdempotencyGuard:
    """In-memory duplicate request blocker with TTL."""

    def __init__(self, *, ttl_sec: float = 300.0) -> None:
        self.ttl_sec = ttl_sec
        self._seen: dict[str, float] = {}
        self._lock = threading.Lock()

    def check_and_set(self, key: str, *, now: float | None = None) -> bool:
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
