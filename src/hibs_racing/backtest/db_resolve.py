"""Resolve a readable SQLite path for offline gate backtests (ramdisk-safe)."""

from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
from pathlib import Path

from hibs_racing.config import ROOT, db_path, load_config


def open_backtest_connection(db: Path) -> sqlite3.Connection:
    """Read-only SQLite open — no init_db, no WAL write (safe for CLI backtests)."""
    uri = f"file:{db.resolve()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=30.0)
    conn.row_factory = sqlite3.Row
    return conn


def _probe_db(path: Path, *, writable: bool = False) -> bool:
    if not path.is_file() or path.stat().st_size <= 0:
        return False
    try:
        conn = sqlite3.connect(str(path), timeout=10.0)
        conn.execute("PRAGMA query_only = ON")
        conn.execute("SELECT 1")
        if writable:
            conn.execute("PRAGMA journal_mode = WAL")
        conn.close()
        return True
    except sqlite3.Error:
        return False


def _candidate_paths(cfg: dict | None = None) -> list[Path]:
    cfg = cfg or load_config()
    out: list[Path] = []
    seen: set[str] = set()

    def _add(raw: str | Path) -> None:
        p = Path(os.path.expanduser(str(raw)))
        key = str(p)
        if key not in seen:
            seen.add(key)
            out.append(p)

    explicit = os.environ.get("HIBS_RACING_DB_PATH")
    use_ram = os.environ.get("HIBS_RACING_BACKTEST_USE_RAMDISK", "").lower() in ("1", "true", "yes")
    if explicit and use_ram:
        _add(explicit)
    _add("/mnt/hibs-racing-data/data/feature_store.sqlite")
    _add(ROOT / "data" / "feature_store.sqlite")
    if explicit:
        _add(explicit)
    _add("/mnt/hibs-ramdisk/feature_store.sqlite")
    _add(db_path(cfg))
    return out


def resolve_backtest_database(
    cfg: dict | None = None,
    *,
    database: Path | None = None,
) -> tuple[Path, str]:
    """
    Pick first usable feature_store for CLI backtests.

  Prefer persistent copies over RAM disk when ramdisk returns disk I/O errors
  or is locked by the live gunicorn worker.
    """
    if database is not None:
        if _probe_db(database):
            return database, "explicit"
        raise FileNotFoundError(f"database not readable: {database}")

    for candidate in _candidate_paths(cfg):
        if _probe_db(candidate):
            return candidate, f"probe_ok:{candidate}"

    # Last resort: copy persist → temp (read-only snapshot, avoids WAL lock on live RAM DB).
    for source in _candidate_paths(cfg):
        if not source.is_file() or source.stat().st_size <= 0:
            continue
        tmp = Path(tempfile.gettempdir()) / f"hibs_backtest_{source.stat().st_size}.sqlite"
        try:
            if not tmp.is_file() or tmp.stat().st_mtime < source.stat().st_mtime:
                shutil.copy2(source, tmp)
            if _probe_db(tmp):
                return tmp, f"snapshot_copy:{source}"
        except OSError:
            continue

    raise FileNotFoundError(
        "no readable feature_store.sqlite — remount ramdisk or restore persist copy:\n"
        "  sudo bash /opt/hibs-racing/deploy/mount-hibs-ramdisk.sh --activate\n"
        "  export HIBS_RACING_DB_PATH=/mnt/hibs-racing-data/data/feature_store.sqlite"
    )
