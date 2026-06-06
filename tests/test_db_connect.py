import sqlite3

import pytest

from hibs_racing.features.store import connect, init_db


def test_connect_closes_and_enables_wal(tmp_path):
    db = tmp_path / "wal.sqlite"
    init_db(db)
    with connect(db) as conn:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert str(mode).lower() == "wal"
        conn.execute("SELECT 1")
    with pytest.raises(sqlite3.ProgrammingError):
        conn.execute("SELECT 1")


def test_connect_rollback_on_error(tmp_path):
    db = tmp_path / "rb.sqlite"
    init_db(db)
    try:
        with connect(db) as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS t (id INTEGER PRIMARY KEY)")
            conn.execute("INSERT INTO t (id) VALUES (1)")
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    probe = sqlite3.connect(db)
    try:
        count = probe.execute("SELECT COUNT(*) FROM t").fetchone()[0]
    except sqlite3.OperationalError:
        count = 0
    finally:
        probe.close()
    assert count == 0
