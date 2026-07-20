"""SQLite integrity check and repair for feature_store.sqlite."""

from __future__ import annotations

import os
import shutil
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from hibs_racing.features.store import SCHEMA_PATH, init_db


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def sqlite_paths(db: Path) -> List[Path]:
    base = Path(db)
    out = [base]
    for suffix in ("-wal", "-shm", "-journal"):
        p = Path(str(base) + suffix)
        if p.is_file():
            out.append(p)
    return out


def integrity_check(db: Path) -> Dict[str, Any]:
    path = Path(db)
    if not path.is_file():
        return {"ok": False, "error": "missing", "path": str(path)}
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5.0)
        try:
            row = conn.execute("PRAGMA integrity_check").fetchone()
            msg = str(row[0]) if row else "unknown"
            ok = msg.lower() == "ok"
            return {"ok": ok, "message": msg, "path": str(path)}
        finally:
            conn.close()
    except sqlite3.DatabaseError as exc:
        return {"ok": False, "error": "database_error", "message": str(exc)[:200], "path": str(path)}
    except Exception as exc:
        return {"ok": False, "error": "check_failed", "message": str(exc)[:200], "path": str(path)}


def _candidate_backups(db: Path) -> List[Path]:
    db = Path(db)
    names = [
        db.with_suffix(db.suffix + ".bak"),
        db.parent / "feature_store.sqlite.bak",
        Path("/mnt/hibs-racing-data/data/feature_store.sqlite"),
        Path("/opt/hibs-racing/data/feature_store.sqlite"),
        db.parent.parent / "data" / "feature_store.sqlite",
    ]
    out: List[Path] = []
    seen: set[str] = set()
    for p in names:
        key = str(p.resolve()) if p.exists() else str(p)
        if key in seen:
            continue
        seen.add(key)
        if p.is_file() and p.resolve() != db.resolve():
            out.append(p)
    return out


def _recover_via_sqlite(db: Path, dest: Path) -> bool:
    if not shutil.which("sqlite3"):
        return False
    try:
        proc = subprocess.run(
            ["sqlite3", str(db), ".recover"],
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            return False
        dest.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["sqlite3", str(dest)],
            input=proc.stdout,
            text=True,
            timeout=300,
            check=True,
        )
        chk = integrity_check(dest)
        return bool(chk.get("ok"))
    except Exception:
        return False


def repair_feature_store(
    db: Path,
    *,
    allow_reinit: bool = True,
) -> Dict[str, Any]:
    """Repair malformed feature_store — backup corrupt, restore or re-init."""
    db = Path(db)
    result: Dict[str, Any] = {
        "path": str(db),
        "action": "none",
        "ok": False,
    }
    chk = integrity_check(db)
    if chk.get("ok"):
        result["ok"] = True
        result["action"] = "already_ok"
        return result

    stamp = _utc_stamp()
    corrupt_dir = db.parent / f".corrupt-{stamp}"
    corrupt_dir.mkdir(parents=True, exist_ok=True)
    for p in sqlite_paths(db):
        if p.is_file():
            shutil.move(str(p), str(corrupt_dir / p.name))

    repaired = db.parent / f"feature_store.repaired-{stamp}.sqlite"
    for backup in _candidate_backups(db):
        bchk = integrity_check(backup)
        if not bchk.get("ok"):
            continue
        try:
            shutil.copy2(backup, repaired)
            if integrity_check(repaired).get("ok"):
                shutil.move(str(repaired), str(db))
                init_db(db)
                result.update({"ok": True, "action": "restored_backup", "source": str(backup)})
                return result
        except OSError:
            continue

    corrupt_file = next(corrupt_dir.glob("feature_store.sqlite"), None)
    if corrupt_file and corrupt_file.is_file() and _recover_via_sqlite(corrupt_file, repaired):
        shutil.move(str(repaired), str(db))
        init_db(db)
        result.update({"ok": True, "action": "sqlite_recover"})
        return result

    if allow_reinit:
        init_db(db)
        result.update({"ok": True, "action": "reinitialized_empty", "warning": "no_valid_backup"})
        return result

    result["action"] = "failed"
    result["corrupt_backup"] = str(corrupt_dir)
    return result


def value_lane_blockers(health: Dict[str, Any]) -> List[str]:
    """Human-readable blockers for value lane (not matchbook creds)."""
    blockers: List[str] = []
    if health.get("db_integrity_ok") is False:
        blockers.append("db_integrity_failed")
    if not health.get("db_ok"):
        blockers.append("db_missing")
    if health.get("card_fresh") is False:
        blockers.append("card_stale")
    unscored = health.get("unscored_runners")
    if unscored is not None and int(unscored) > 0:
        blockers.append(f"unscored_runners={unscored}")
    if health.get("nan_integrity_passed") is False:
        blockers.append("nan_integrity_failed")
    if health.get("runners_loaded", 0) == 0:
        blockers.append("no_runners_loaded")
    return blockers
