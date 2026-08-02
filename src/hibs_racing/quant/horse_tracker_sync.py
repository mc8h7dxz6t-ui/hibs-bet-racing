"""Sync racing card horses to quant platform horse_registry + horse_tracker."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

_HORSE_DDL = """
CREATE TABLE IF NOT EXISTS horse_registry (
    horse_id TEXT PRIMARY KEY,
    canonical_name TEXT NOT NULL,
    aliases_json TEXT,
    sex TEXT,
    foaling_year INTEGER,
    sire TEXT,
    dam TEXT,
    first_seen TEXT,
    last_seen TEXT,
    provenance TEXT
);

CREATE TABLE IF NOT EXISTS horse_tracker (
    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
    horse_id TEXT NOT NULL,
    race_uid TEXT NOT NULL,
    run_date TEXT NOT NULL,
    course TEXT,
    position INTEGER,
    or_rating REAL,
    rtf REAL,
    source_hash TEXT,
    ingested_at TEXT NOT NULL,
    UNIQUE(horse_id, race_uid)
);

CREATE INDEX IF NOT EXISTS idx_horse_tracker_horse ON horse_tracker(horse_id, run_date);
"""


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def resolve_quant_data_plane_db() -> Path:
    for key in ("QUANT_DATA_PLANE_DB", "HIBS_QUANT_DATA_PLANE_DB"):
        raw = (os.getenv(key) or "").strip()
        if raw:
            return Path(raw)
    football_root = (os.getenv("QUANT_FOOTBALL_PATH") or os.getenv("HIBS_FOOTBALL_PATH") or "").strip()
    if football_root:
        return Path(football_root) / "data" / "quant_platform.sqlite"
    return Path("data/quant_platform.sqlite")


def quant_sync_enabled() -> bool:
    flag = (os.getenv("QUANT_HORSE_TRACKER_SYNC") or os.getenv("HIBS_QUANT_HORSE_TRACKER_SYNC") or "1").strip().lower()
    return flag not in ("0", "false", "no", "off")


def _init_quant_horse_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(_HORSE_DDL)


def _row_source_hash(rec: dict[str, Any]) -> str:
    body = json.dumps(rec, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _upsert_horse(conn: sqlite3.Connection, horse_id: str, name: str, now: str) -> None:
    conn.execute(
        """
        INSERT INTO horse_registry (horse_id, canonical_name, first_seen, last_seen, provenance)
        VALUES (?, ?, ?, ?, 'racing_card_sync')
        ON CONFLICT(horse_id) DO UPDATE SET
            canonical_name=excluded.canonical_name,
            last_seen=excluded.last_seen
        """,
        (horse_id, name or horse_id, now, now),
    )


def _upsert_tracker_run(
    conn: sqlite3.Connection,
    *,
    horse_id: str,
    race_uid: str,
    run_date: str,
    course: str,
    or_rating: float | None,
    rtf: float | None,
    source_hash: str,
    now: str,
) -> None:
    conn.execute(
        """
        INSERT INTO horse_tracker (
            horse_id, race_uid, run_date, course, position, or_rating, rtf,
            source_hash, ingested_at
        ) VALUES (?, ?, ?, ?, NULL, ?, ?, ?, ?)
        ON CONFLICT(horse_id, race_uid) DO UPDATE SET
            run_date=excluded.run_date,
            course=excluded.course,
            or_rating=excluded.or_rating,
            rtf=excluded.rtf,
            source_hash=excluded.source_hash,
            ingested_at=excluded.ingested_at
        """,
        (horse_id, race_uid, run_date, course, or_rating, rtf, source_hash, now),
    )


def sync_card_horses_to_quant_plane(frame: pd.DataFrame) -> dict[str, Any]:
    """
    Upsert horses from an upcoming card frame into quant platform SQLite.
    No-op when sync disabled or frame empty.
    """
    if not quant_sync_enabled():
        return {"ok": True, "skipped": True, "reason": "sync_disabled"}
    if frame is None or frame.empty:
        return {"ok": True, "skipped": True, "reason": "empty_frame"}

    db_path = resolve_quant_data_plane_db()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    now = _now()
    horses = 0
    runs = 0

    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        _init_quant_horse_tables(conn)
        for rec in frame.to_dict(orient="records"):
            horse_id = str(rec.get("horse_id") or "").strip()
            if not horse_id:
                continue
            name = str(rec.get("horse_name") or horse_id)
            _upsert_horse(conn, horse_id, name, now)
            horses += 1

            race_uid = str(rec.get("race_natural_key") or rec.get("race_id") or rec.get("runner_id") or "")
            if not race_uid:
                continue
            run_date = str(rec.get("card_date") or "")
            course = str(rec.get("course") or "")
            or_rating = rec.get("official_rating")
            rtf = rec.get("trainer_rtf")
            try:
                or_rating = float(or_rating) if or_rating is not None else None
            except (TypeError, ValueError):
                or_rating = None
            try:
                rtf = float(rtf) if rtf is not None else None
            except (TypeError, ValueError):
                rtf = None
            src = _row_source_hash(
                {
                    "horse_id": horse_id,
                    "race_uid": race_uid,
                    "run_date": run_date,
                    "runner_id": rec.get("runner_id"),
                }
            )
            _upsert_tracker_run(
                conn,
                horse_id=horse_id,
                race_uid=race_uid,
                run_date=run_date,
                course=course,
                or_rating=or_rating,
                rtf=rtf,
                source_hash=src,
                now=now,
            )
            runs += 1
        conn.commit()
    finally:
        conn.close()

    result = {
        "ok": True,
        "db_path": str(db_path),
        "horses_upserted": horses,
        "tracker_runs_upserted": runs,
    }
    logger.info("quant horse tracker sync: %s", result)
    return result
