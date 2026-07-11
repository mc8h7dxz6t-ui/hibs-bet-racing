"""Process-wide ledger singleton — avoid O(n) WAL replay per request."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from inst_spine.ledger import AppendOnlyLedger

_lock = threading.Lock()
_ledgers: dict[tuple[str, str, bool], AppendOnlyLedger] = {}


def get_ledger(
    database: Path,
    *,
    writer_id: str = "default",
    async_writes: bool = False,
) -> AppendOnlyLedger:
    """Return cached AppendOnlyLedger for (path, writer_id, async_writes)."""
    key = (str(Path(database).resolve()), writer_id, async_writes)
    with _lock:
        existing = _ledgers.get(key)
        if existing is not None:
            return existing
        ledger = AppendOnlyLedger(
            Path(database),
            writer_id=writer_id,
            async_writes=async_writes,
        )
        _ledgers[key] = ledger
        return ledger


def clear_ledger_registry() -> None:
    """Test helper — shutdown cached ledgers."""
    with _lock:
        for ledger in _ledgers.values():
            if ledger._async:
                ledger.stop_async_writer(flush=True)
        _ledgers.clear()
