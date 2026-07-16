from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hibs_racing.features.store import connect
from hibs_racing.models.win_engine_config import (
    CALIBRATION_CALIBRATED,
    CALIBRATION_UNCALIBRATED,
)

WIN_ENGINE_DDL = """
CREATE TABLE IF NOT EXISTS win_engine_predictions (
    runner_id           TEXT PRIMARY KEY,
    race_id             TEXT NOT NULL,
    true_probability    REAL NOT NULL,
    fair_odds           REAL NOT NULL,
    brier_score         REAL,
    place_probability   REAL,
    live_odds_decimal   REAL,
    x_fund              REAL,
    market_velocity     REAL,
    timestamp           TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_win_engine_race ON win_engine_predictions (race_id);
CREATE INDEX IF NOT EXISTS idx_win_engine_ts ON win_engine_predictions (timestamp);

CREATE TABLE IF NOT EXISTS win_engine_calibration (
    id                  INTEGER PRIMARY KEY CHECK (id = 1),
    calibration_state   TEXT NOT NULL DEFAULT 'UNCALIBRATED',
    rolling_brier       REAL,
    sample_n            INTEGER NOT NULL DEFAULT 0,
    races_in_window     INTEGER NOT NULL DEFAULT 0,
    updated_at          TEXT NOT NULL
);
"""


def ensure_win_engine_schema(db: Path) -> None:
    with connect(db) as conn:
        conn.executescript(WIN_ENGINE_DDL)
        conn.execute(
            """
            INSERT OR IGNORE INTO win_engine_calibration (id, calibration_state, updated_at)
            VALUES (1, ?, datetime('now'))
            """,
            (CALIBRATION_UNCALIBRATED,),
        )


def upsert_predictions(conn: sqlite3.Connection, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    n = 0
    for row in rows:
        conn.execute(
            """
            INSERT INTO win_engine_predictions (
                runner_id, race_id, true_probability, fair_odds, brier_score,
                place_probability, live_odds_decimal, x_fund, market_velocity, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(runner_id) DO UPDATE SET
                race_id = excluded.race_id,
                true_probability = excluded.true_probability,
                fair_odds = excluded.fair_odds,
                place_probability = excluded.place_probability,
                live_odds_decimal = excluded.live_odds_decimal,
                x_fund = excluded.x_fund,
                market_velocity = excluded.market_velocity,
                timestamp = excluded.timestamp
            """,
            (
                row["runner_id"],
                row["race_id"],
                row["true_probability"],
                row["fair_odds"],
                row.get("brier_score"),
                row.get("place_probability"),
                row.get("live_odds_decimal"),
                row.get("x_fund"),
                row.get("market_velocity"),
                row.get("timestamp") or now,
            ),
        )
        n += 1
    return n


def load_predictions_for_date(conn: sqlite3.Connection, card_date: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT w.*, u.horse_name, u.course, u.off_time, u.card_date
        FROM win_engine_predictions w
        JOIN upcoming_runners u ON u.runner_id = w.runner_id
        WHERE u.card_date = ?
        ORDER BY w.race_id, w.true_probability DESC
        """,
        (card_date,),
    ).fetchall()
    return [dict(r) for r in rows]


def load_calibration_state(conn: sqlite3.Connection) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM win_engine_calibration WHERE id = 1").fetchone()
    if not row:
        return {
            "calibration_state": CALIBRATION_UNCALIBRATED,
            "rolling_brier": None,
            "sample_n": 0,
            "races_in_window": 0,
        }
    return dict(row)


def update_calibration_state(
    conn: sqlite3.Connection,
    *,
    calibration_state: str,
    rolling_brier: float | None,
    sample_n: int,
    races_in_window: int,
) -> None:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    conn.execute(
        """
        UPDATE win_engine_calibration
        SET calibration_state = ?, rolling_brier = ?, sample_n = ?, races_in_window = ?, updated_at = ?
        WHERE id = 1
        """,
        (calibration_state, rolling_brier, sample_n, races_in_window, now),
    )


def is_calibrated(conn: sqlite3.Connection) -> bool:
    state = load_calibration_state(conn)
    return state.get("calibration_state") == CALIBRATION_CALIBRATED
