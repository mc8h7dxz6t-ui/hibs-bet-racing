"""Append-only WAL — synchronous durability before SQLite write-behind."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Iterator


class AppendOnlyWal:
    """Line-delimited JSON WAL with fsync on every append."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def append(self, record: dict[str, Any]) -> None:
        line = json.dumps(record, sort_keys=True, default=str, separators=(",", ":")) + "\n"
        with self._lock:
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(line)
                fh.flush()
                os.fsync(fh.fileno())

    def iter_records(self) -> Iterator[dict[str, Any]]:
        if not self.path.exists():
            return iter(())
        records: list[dict[str, Any]] = []

        def _gen() -> Iterator[dict[str, Any]]:
            with open(self.path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    records.append(json.loads(line))
            yield from records

        return _gen()

    def read_all(self) -> list[dict[str, Any]]:
        return list(self.iter_records())

    def tail_hash(self) -> str | None:
        records = self.read_all()
        if not records:
            return None
        return str(records[-1].get("entry_hash") or "")

    def count(self) -> int:
        if not self.path.exists():
            return 0
        n = 0
        with open(self.path, encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    n += 1
        return n


class WALWriter:
    """
    Sync WAL facade for webhook ingress hot path.
    Every append fsyncs before HTTP 200 — survives kill -9.
    """

    def __init__(self, path: str | Path) -> None:
        self._wal = AppendOnlyWal(Path(path))

    def append(
        self,
        *,
        payload: dict[str, Any],
        lamport: int,
        raw_bytes: bytes | None = None,
    ) -> None:
        import hashlib

        record = dict(payload)
        record["lamport_seq"] = lamport
        if raw_bytes is not None:
            record["payload_sha256"] = hashlib.sha256(raw_bytes).hexdigest()
            record["payload_size"] = len(raw_bytes)
        self._wal.append(record)

    def close(self) -> None:
        """No persistent handle — append opens/closes per write."""
        return None

    @property
    def path(self) -> Path:
        return self._wal.path
