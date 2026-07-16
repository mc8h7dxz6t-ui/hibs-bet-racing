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
    timestamp           TEXT NOT NULL,
    matchbook_back_odds REAL,
    race_field_brier    REAL,
    market_race_brier   REAL,
    field_size          INTEGER
);

CREATE INDEX IF NOT EXISTS idx_win_engine_race ON win_engine_predictions (race_id);
CREATE INDEX IF NOT EXISTS idx_win_engine_ts ON win_engine_predictions (timestamp);

CREATE TABLE IF NOT EXISTS win_engine_calibration (
    id                      INTEGER PRIMARY KEY CHECK (id = 1),
    calibration_state       TEXT NOT NULL DEFAULT 'UNCALIBRATED',
    rolling_brier           REAL,
    sample_n                INTEGER NOT NULL DEFAULT 0,
    races_in_window         INTEGER NOT NULL DEFAULT 0,
    updated_at              TEXT NOT NULL,
    market_brier_rolling    REAL,
    exchange_beat_delta_bps REAL,
    variable_bounds_pass    INTEGER NOT NULL DEFAULT 0,
    market_beat_pass        INTEGER NOT NULL DEFAULT 0
);
"""

WIN_ENGINE_PREDICTIONS_MIGRATIONS: tuple[tuple[str, str], ...] = (
    ("matchbook_back_odds", "REAL"),
    ("race_field_brier", "REAL"),
    ("market_race_brier", "REAL"),
    ("field_size", "INTEGER"),
)

WIN_ENGINE_CALIBRATION_MIGRATIONS: tuple[tuple[str, str], ...] = (
    ("market_brier_rolling", "REAL"),
    ("exchange_beat_delta_bps", "REAL"),
    ("variable_bounds_pass", "INTEGER NOT NULL DEFAULT 0"),
    ("market_beat_pass", "INTEGER NOT NULL DEFAULT 0"),
)


def _migrate_columns(conn: sqlite3.Connection, table: str, migrations: tuple[tuple[str, str], ...]) -> None:
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if not existing:
        return
    for column, typedef in migrations:
        if column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {typedef}")


def ensure_win_engine_schema(db: Path) -> None:
    with connect(db) as conn:
        conn.executescript(WIN_ENGINE_DDL)
        _migrate_columns(conn, "win_engine_predictions", WIN_ENGINE_PREDICTIONS_MIGRATIONS)
        _migrate_columns(conn, "win_engine_calibration", WIN_ENGINE_CALIBRATION_MIGRATIONS)
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
                place_probability, live_odds_decimal, x_fund, market_velocity, timestamp,
                matchbook_back_odds, race_field_brier, market_race_brier, field_size
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(runner_id) DO UPDATE SET
                race_id = excluded.race_id,
                true_probability = excluded.true_probability,
                fair_odds = excluded.fair_odds,
                place_probability = excluded.place_probability,
                live_odds_decimal = excluded.live_odds_decimal,
                x_fund = excluded.x_fund,
                market_velocity = excluded.market_velocity,
                timestamp = excluded.timestamp,
                matchbook_back_odds = excluded.matchbook_back_odds,
                field_size = excluded.field_size
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
                row.get("matchbook_back_odds"),
                row.get("race_field_brier"),
                row.get("market_race_brier"),
                row.get("field_size"),
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
            "market_brier_rolling": None,
            "exchange_beat_delta_bps": None,
            "variable_bounds_pass": False,
            "market_beat_pass": False,
        }
    out = dict(row)
    out["variable_bounds_pass"] = bool(out.get("variable_bounds_pass"))
    out["market_beat_pass"] = bool(out.get("market_beat_pass"))
    return out


def update_calibration_state(
    conn: sqlite3.Connection,
    *,
    calibration_state: str,
    rolling_brier: float | None,
    sample_n: int,
    races_in_window: int,
    market_brier_rolling: float | None = None,
    exchange_beat_delta_bps: float | None = None,
    variable_bounds_pass: bool = False,
    market_beat_pass: bool = False,
) -> None:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    conn.execute(
        """
        UPDATE win_engine_calibration
        SET calibration_state = ?,
            rolling_brier = ?,
            sample_n = ?,
            races_in_window = ?,
            updated_at = ?,
            market_brier_rolling = ?,
            exchange_beat_delta_bps = ?,
            variable_bounds_pass = ?,
            market_beat_pass = ?
        WHERE id = 1
        """,
        (
            calibration_state,
            rolling_brier,
            sample_n,
            races_in_window,
            now,
            market_brier_rolling,
            exchange_beat_delta_bps,
            1 if variable_bounds_pass else 0,
            1 if market_beat_pass else 0,
        ),
    )


def is_calibrated(conn: sqlite3.Connection) -> bool:
    state = load_calibration_state(conn)
    return state.get("calibration_state") == CALIBRATION_CALIBRATED
