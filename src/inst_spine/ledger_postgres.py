"""Postgres append-only ledger — production HA profile for Compliance Logger (#1)."""

from __future__ import annotations

import json
import os
import threading
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
CREATE TABLE IF NOT EXISTS inst_ledger_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def _import_psycopg():
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError(
            "Postgres ledger requires: pip install 'hibs-racing[postgres]'"
        ) from exc
    return psycopg


class PostgresAppendOnlyLedger:
    """Same public API as AppendOnlyLedger — durable index in Postgres + local WAL."""

    def __init__(
        self,
        dsn: str,
        *,
        writer_id: str = "default",
        config_hash: str | None = None,
        async_writes: bool = False,
        wal_dir: Path | None = None,
    ) -> None:
        if async_writes:
            raise ValueError("Postgres ledger uses synchronous writes — async_writes=False")
        self.dsn = dsn.strip()
        self.writer_id = writer_id
        self.config_hash = config_hash or stable_id(writer_id, "config", "v1")
        wal_root = wal_dir or Path(os.getenv("INST_LEDGER_WAL_DIR", "data/wal"))
        wal_root.mkdir(parents=True, exist_ok=True)
        slug = stable_id(self.dsn)[:16]
        self.wal_path = wal_root / f"pg_ledger_{slug}.wal"
        self.anchor_path = wal_root / f"pg_ledger_{slug}.genesis.json"
        self.wal = AppendOnlyWal(self.wal_path)
        self.clock = LamportClock(writer_id)
        self._lock = threading.Lock()
        self._last_hash = ""
        self._instance_uuid = ""
        psycopg = _import_psycopg()
        with psycopg.connect(self.dsn) as conn:
            for part in _SCHEMA.split(";"):
                sql = part.strip()
                if sql:
                    conn.execute(sql)
            conn.commit()
        self._ensure_genesis()
        self._replay_wal_to_postgres()
        self._load_tail_state()

    def _connect(self):
        psycopg = _import_psycopg()
        return psycopg.connect(self.dsn)

    def _ensure_genesis(self) -> None:
        wal_records = self.wal.read_all()
        genesis_wal = next((r for r in wal_records if r.get("event_type") == GENESIS_EVENT), None)
        if genesis_wal:
            self._instance_uuid = str((genesis_wal.get("payload") or {}).get("instance_uuid") or "")
            self._last_hash = str(genesis_wal.get("entry_hash") or "")
            return

        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload_json, entry_hash FROM inst_ledger WHERE event_type = %s LIMIT 1",
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

    def _replay_wal_to_postgres(self) -> None:
        existing = self._postgres_entry_ids()
        for record in self.wal.read_all():
            eid = str(record.get("entry_id") or "")
            if eid and eid not in existing:
                self._persist_record(record)

    def _postgres_entry_ids(self) -> set[str]:
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
        return

    def stop_async_writer(self, *, flush: bool = True) -> None:
        return

    def close(self) -> None:
        return

    def __enter__(self) -> PostgresAppendOnlyLedger:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def flush(self) -> int:
        return 0

    def append(
        self,
        *,
        event_type: str,
        payload: dict[str, Any],
        manifest_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> LedgerEntry:
        if event_type == GENESIS_EVENT:
            raise ValueError("genesis block is immutable")

        with self._lock:
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
            self.wal.append(record)
            self._last_hash = entry_hash
            self._persist_record(record)

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

    def _persist_record(self, record: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO inst_ledger (
                    entry_id, event_type, writer_id, lamport_seq, wall_time_utc,
                    manifest_id, payload_json, metadata_json, prev_hash, entry_hash
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (entry_id) DO NOTHING
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
        records = self.wal.read_all()
        if limit and len(records) > limit:
            records = records[:limit]
        return records

    def verify(self) -> dict[str, Any]:
        entries = self.list_entries()
        anchor = read_genesis_anchor(self.anchor_path)
        genesis_row = entries[0] if entries else None
        genesis = verify_genesis_block(genesis_row, anchor=anchor)
        chain = verify_chain(entries, anchor=anchor, require_genesis=True)
        lamport_ok = verify_lamport_monotonic(entries)
        pg_gap = self.wal.count() - len(self._postgres_entry_ids())
        return {
            "chain_ok": chain.ok and genesis.ok,
            "chain_message": chain.message if chain.ok else (genesis.message if not genesis.ok else chain.message),
            "genesis_ok": genesis.ok,
            "genesis_message": genesis.message,
            "entries_checked": chain.entries_checked,
            "first_mismatch_index": chain.first_mismatch_index,
            "lamport_monotonic": lamport_ok,
            "wal_records": self.wal.count(),
            "wal_sqlite_pending": max(0, pg_gap),
            "instance_uuid": self._instance_uuid,
            "backend": "postgres",
        }

    @property
    def database(self) -> str:
        return self.dsn
