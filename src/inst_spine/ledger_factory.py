"""Open institutional ledger — SQLite path (default) or Postgres DSN."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from inst_spine.ledger import AppendOnlyLedger


def is_postgres_dsn(value: str | Path) -> bool:
    text = str(value).strip().lower()
    return text.startswith("postgresql://") or text.startswith("postgres://")


def open_ledger(database: Path | str, **kwargs: Any) -> AppendOnlyLedger:
    """
    Open append-only ledger.

    - Path ending in .sqlite → SQLite + WAL (default VPC)
    - postgres:// or postgresql:// DSN → Postgres profile (multi-writer HA)
    """
    if is_postgres_dsn(database):
        from inst_spine.ledger_postgres import PostgresAppendOnlyLedger

        return PostgresAppendOnlyLedger(str(database), **kwargs)
    return AppendOnlyLedger(Path(database), **kwargs)
