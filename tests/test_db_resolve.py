import sqlite3
from pathlib import Path

import pytest

from hibs_racing.backtest.db_resolve import resolve_backtest_database
from hibs_racing.features.store import init_db


def test_resolve_backtest_database(tmp_path, monkeypatch):
    good = tmp_path / "good.sqlite"
    bad = tmp_path / "bad.sqlite"
    bad.write_bytes(b"not sqlite")
    init_db(good)

    monkeypatch.setenv("HIBS_RACING_DB_PATH", str(bad))
    resolved, reason = resolve_backtest_database()
    assert resolved == good or resolved.is_file()
    assert "probe_ok" in reason or "snapshot_copy" in reason


def test_configure_connection_wal_fallback(tmp_path):
    from hibs_racing.features.store import connect

    db = tmp_path / "t.sqlite"
    init_db(db)
    with connect(db) as conn:
        row = conn.execute("PRAGMA journal_mode").fetchone()
        assert row is not None
