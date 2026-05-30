from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hibs_racing.features.store import connect, init_db

TIPSTER_TIPS_DDL = """
CREATE TABLE IF NOT EXISTS tipster_tips (
    tip_id              TEXT PRIMARY KEY,
    email_message_id    TEXT,
    source_file         TEXT,
    source_kind         TEXT,
    received_at         TEXT,
    subject             TEXT,
    card_date           TEXT,
    horse_name          TEXT,
    course              TEXT,
    off_time            TEXT,
    odds_quoted         TEXT,
    odds_decimal        REAL,
    bet_type            TEXT NOT NULL DEFAULT 'unknown',
    stable_intel        TEXT NOT NULL DEFAULT 'unknown',
    confidence          TEXT,
    raw_excerpt         TEXT,
    tipster_review      TEXT,
    raw_email_body      TEXT,
    runner_id           TEXT,
    race_id             TEXT,
    match_status        TEXT NOT NULL DEFAULT 'unmatched',
    finish_pos          INTEGER,
    won                 INTEGER,
    placed              INTEGER,
    result_sp           REAL,
    settled_at          TEXT,
    ingested_at         TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tips_date ON tipster_tips (card_date);
CREATE INDEX IF NOT EXISTS idx_tips_stable ON tipster_tips (stable_intel);
CREATE INDEX IF NOT EXISTS idx_tips_match ON tipster_tips (match_status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_tips_dedup
    ON tipster_tips (email_message_id, horse_name, course, off_time, card_date);
"""


def ensure_tipster_schema(db: Path) -> None:
    init_db(db)
    with connect(db) as conn:
        conn.executescript(TIPSTER_TIPS_DDL)
        existing = {row[1] for row in conn.execute("PRAGMA table_info(tipster_tips)").fetchall()}
        if existing and "tipster_review" not in existing:
            conn.execute("ALTER TABLE tipster_tips ADD COLUMN tipster_review TEXT")
        conn.commit()


def _tip_id(message_id: str, horse: str | None, course: str | None, off_time: str | None, card_date: str | None) -> str:
    raw = "|".join(
        [
            message_id or "",
            (horse or "").lower().strip(),
            (course or "").lower().strip(),
            off_time or "",
            card_date or "",
        ]
    )
    return hashlib.sha256(raw.encode()).hexdigest()[:20]


def insert_tip(
    conn: sqlite3.Connection,
    *,
    email_message_id: str,
    source_file: str,
    source_kind: str,
    received_at: str | None,
    subject: str,
    card_date: str | None,
    horse_name: str | None,
    course: str | None,
    off_time: str | None,
    odds_quoted: str | None,
    odds_decimal: float | None,
    bet_type: str,
    stable_intel: str,
    confidence: str | None,
    raw_excerpt: str,
    raw_email_body: str | None = None,
    tipster_review: str | None = None,
) -> tuple[str, bool]:
    """Returns (tip_id, inserted). False if duplicate."""
    tip_id = _tip_id(email_message_id, horse_name, course, off_time, card_date)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    try:
        conn.execute(
            """
            INSERT INTO tipster_tips (
                tip_id, email_message_id, source_file, source_kind, received_at, subject,
                card_date, horse_name, course, off_time, odds_quoted, odds_decimal,
                bet_type, stable_intel, confidence, raw_excerpt, tipster_review, raw_email_body,
                ingested_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tip_id,
                email_message_id,
                source_file,
                source_kind,
                received_at,
                subject,
                card_date,
                horse_name,
                course,
                off_time,
                odds_quoted,
                odds_decimal,
                bet_type,
                stable_intel,
                confidence,
                raw_excerpt,
                tipster_review,
                raw_email_body,
                now,
            ),
        )
        return tip_id, True
    except sqlite3.IntegrityError:
        return tip_id, False


def update_tip_match(
    conn: sqlite3.Connection,
    tip_id: str,
    *,
    runner_id: str | None,
    race_id: str | None,
    match_status: str,
) -> None:
    conn.execute(
        """
        UPDATE tipster_tips
        SET runner_id = ?, race_id = ?, match_status = ?
        WHERE tip_id = ?
        """,
        (runner_id, race_id, match_status, tip_id),
    )


def update_tip_settlement(
    conn: sqlite3.Connection,
    tip_id: str,
    *,
    finish_pos: int | None,
    won: int,
    placed: int,
    result_sp: float | None,
) -> None:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    conn.execute(
        """
        UPDATE tipster_tips
        SET finish_pos = ?, won = ?, placed = ?, result_sp = ?, settled_at = ?
        WHERE tip_id = ?
        """,
        (finish_pos, won, placed, result_sp, now, tip_id),
    )


def load_tips(
    db: Path,
    *,
    unsettled_only: bool = False,
    limit: int = 500,
) -> list[dict[str, Any]]:
    ensure_tipster_schema(db)
    sql = "SELECT * FROM tipster_tips"
    if unsettled_only:
        sql += " WHERE settled_at IS NULL"
    sql += " ORDER BY card_date DESC, received_at DESC LIMIT ?"
    with connect(db) as conn:
        rows = conn.execute(sql, (limit,)).fetchall()
    return [dict(r) for r in rows]


def tipster_summary(db: Path) -> dict[str, Any]:
    ensure_tipster_schema(db)
    with connect(db) as conn:
        total = conn.execute("SELECT COUNT(*) FROM tipster_tips").fetchone()[0]
        settled = conn.execute("SELECT COUNT(*) FROM tipster_tips WHERE settled_at IS NOT NULL").fetchone()[0]
        wins = conn.execute("SELECT COUNT(*) FROM tipster_tips WHERE won = 1").fetchone()[0]
        places = conn.execute("SELECT COUNT(*) FROM tipster_tips WHERE placed = 1").fetchone()[0]
        stable = conn.execute(
            "SELECT COUNT(*) FROM tipster_tips WHERE stable_intel = 'yes'"
        ).fetchone()[0]
        stable_wins = conn.execute(
            "SELECT COUNT(*) FROM tipster_tips WHERE stable_intel = 'yes' AND won = 1"
        ).fetchone()[0]
        non_stable_settled = conn.execute(
            "SELECT COUNT(*) FROM tipster_tips WHERE stable_intel != 'yes' AND settled_at IS NOT NULL"
        ).fetchone()[0]
        non_stable_wins = conn.execute(
            "SELECT COUNT(*) FROM tipster_tips WHERE stable_intel != 'yes' AND won = 1"
        ).fetchone()[0]
    return {
        "total_tips": total,
        "settled": settled,
        "wins": wins,
        "places": places,
        "win_pct": round(100 * wins / settled, 1) if settled else None,
        "place_pct": round(100 * places / settled, 1) if settled else None,
        "stable_tagged": stable,
        "stable_wins": stable_wins,
        "non_stable_settled": non_stable_settled,
        "non_stable_wins": non_stable_wins,
        "non_stable_win_pct": round(100 * non_stable_wins / non_stable_settled, 1)
        if non_stable_settled
        else None,
    }
