"""Open spend wallet — SQLite (default) or Postgres DSN."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Union

from inst_spine.ledger_factory import is_postgres_dsn
from spend_guard.wallet import SpendWallet

Wallet = Union[SpendWallet, "PostgresSpendWallet"]


def open_wallet(database: Path | str, **kwargs: Any) -> Wallet:
    if is_postgres_dsn(database):
        from spend_guard.postgres_wallet import PostgresSpendWallet

        return PostgresSpendWallet(str(database), **kwargs)
    return SpendWallet(Path(database), **kwargs)
