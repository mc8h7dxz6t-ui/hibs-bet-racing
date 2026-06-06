from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

SCHEMA_PATH = Path(__file__).resolve().parents[3] / "data" / "schema.sql"

SECTIONAL_MIGRATIONS: tuple[tuple[str, str], ...] = (
    ("late_pace_level", "INTEGER NOT NULL DEFAULT 0"),
    ("finishing_burst_level", "INTEGER NOT NULL DEFAULT 0"),
    ("stamina_deficit_flag", "INTEGER NOT NULL DEFAULT 0"),
    ("headway_at_furlongs", "REAL"),
    ("fade_in_final_furlong", "INTEGER NOT NULL DEFAULT 0"),
    ("quickened_to_lead", "INTEGER NOT NULL DEFAULT 0"),
    ("sectional_composite", "REAL NOT NULL DEFAULT 0"),
    ("parser_backend", "TEXT NOT NULL DEFAULT 'regex'"),
)

RUNNER_MIGRATIONS: tuple[tuple[str, str], ...] = (
    ("jockey", "TEXT"),
    ("trainer", "TEXT"),
    ("draw", "INTEGER"),
    ("official_rating", "INTEGER"),
    ("rpr", "INTEGER"),
    ("race_class", "TEXT"),
    ("days_since_last_run", "INTEGER"),
)

UPCOMING_MIGRATIONS: tuple[tuple[str, str], ...] = (
    ("win_decimal", "REAL"),
    ("race_natural_key", "TEXT"),
    ("form_string", "TEXT"),
    ("trainer_rtf", "REAL"),
    ("trainer_14d_wins", "INTEGER"),
    ("trainer_14d_runs", "INTEGER"),
    ("trainer_location", "TEXT"),
    ("distance_f", "REAL"),
    ("place_fraction", "REAL"),
    ("places", "INTEGER"),
    ("offered_place_decimal", "REAL"),
    ("rp_verdict", "TEXT"),
    ("horse_course_wins", "INTEGER"),
    ("horse_course_runs", "INTEGER"),
    ("horse_course_win_rate", "REAL"),
    ("horse_distance_wins", "INTEGER"),
    ("horse_distance_runs", "INTEGER"),
    ("horse_distance_win_rate", "REAL"),
    ("horse_going_wins", "INTEGER"),
    ("horse_going_runs", "INTEGER"),
    ("horse_going_win_rate", "REAL"),
    ("jockey_rp_14d_wins", "INTEGER"),
    ("jockey_rp_14d_runs", "INTEGER"),
    ("jockey_rp_14d_win_rate", "REAL"),
    ("jockey_rp_14d_wins_pct", "REAL"),
    ("trainer_rp_14d_wins", "INTEGER"),
    ("trainer_rp_14d_runs", "INTEGER"),
    ("trainer_rp_14d_win_rate", "REAL"),
    ("trainer_rp_14d_wins_pct", "REAL"),
    ("form_lto_position", "INTEGER"),
    ("form_trip_change_f", "REAL"),
    ("form_cd_flag", "INTEGER"),
    ("form_bf_flag", "INTEGER"),
    ("form_poor_runs_3", "INTEGER"),
    ("trainer_14d_strike", "REAL"),
    ("enrich_source", "TEXT"),
    ("enriched_at", "TEXT"),
)

CARD_SCORES_MIGRATIONS: tuple[tuple[str, str], ...] = (
    ("scoring_method", "TEXT"),
    ("jockey_bayes_place", "REAL"),
    ("trainer_bayes_place", "REAL"),
    ("jockey_place_90d", "REAL"),
    ("trainer_place_90d", "REAL"),
    ("value_gate_reason", "TEXT"),
)

RUNNER_NATURAL_MIGRATIONS: tuple[tuple[str, str], ...] = (
    ("off_time", "TEXT"),
    ("race_natural_key", "TEXT"),
    ("distance_f", "REAL"),
)

# Enrich spine for historical LTR — mirrors upcoming_runners ranker inputs.
RUNNER_ENRICH_MIGRATIONS: tuple[tuple[str, str], ...] = (
    ("form_string", "TEXT"),
    ("trainer_14d_wins", "INTEGER"),
    ("trainer_14d_runs", "INTEGER"),
    ("horse_course_win_rate", "REAL"),
    ("horse_distance_win_rate", "REAL"),
    ("horse_going_win_rate", "REAL"),
    ("jockey_rp_14d_win_rate", "REAL"),
    ("trainer_rp_14d_win_rate", "REAL"),
    ("trainer_rtf", "REAL"),
    ("trainer_14d_strike", "REAL"),
    ("form_lto_position", "INTEGER"),
    ("form_trip_change_f", "REAL"),
    ("form_cd_flag", "INTEGER"),
    ("form_bf_flag", "INTEGER"),
    ("form_poor_runs_3", "INTEGER"),
    ("enrich_source", "TEXT"),
    ("enriched_at", "TEXT"),
)

EXECUTION_LOG_MIGRATIONS: tuple[tuple[str, str], ...] = (
    ("matchbook_place_market_id", "INTEGER"),
    ("betfair_place_market_id", "TEXT"),
)

PAPER_BETS_MIGRATIONS: tuple[tuple[str, str], ...] = (
    ("is_value_pick", "INTEGER NOT NULL DEFAULT 0"),
    ("finish_pos", "INTEGER"),
    ("closing_sp", "REAL"),
    ("clv_beat", "INTEGER"),
    ("verification_hash", "TEXT"),
    ("backtest", "INTEGER NOT NULL DEFAULT 0"),
)

SNAPSHOT_MIGRATIONS: tuple[tuple[str, str], ...] = (
    ("gates_json", "TEXT"),
)


def _configure_connection(conn: sqlite3.Connection) -> sqlite3.Connection:
    """Institutional++ SQLite defaults — WAL readers, writer busy wait, FK enforcement."""
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


@contextmanager
def connect(db: Path) -> Iterator[sqlite3.Connection]:
    """
    Open SQLite with guaranteed close on exit.

    Python's sqlite3 connection context manager commits but does not close —
    leaking file descriptors across refresh loops until EMFILE (Jun 5 cron).
    """
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db), timeout=30.0)
    _configure_connection(conn)
    try:
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def _migrate_columns(conn: sqlite3.Connection, table: str, migrations: tuple[tuple[str, str], ...]) -> None:
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if not existing:
        return
    for column, typedef in migrations:
        if column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {typedef}")


def init_db(db: Path) -> None:
    sql = SCHEMA_PATH.read_text(encoding="utf-8")
    with connect(db) as conn:
        conn.executescript(sql)
        _migrate_columns(conn, "comment_tags", SECTIONAL_MIGRATIONS)
        _migrate_columns(conn, "runners", RUNNER_MIGRATIONS)
        _migrate_columns(conn, "runners", RUNNER_NATURAL_MIGRATIONS)
        _migrate_columns(conn, "runners", RUNNER_ENRICH_MIGRATIONS)
        _migrate_columns(conn, "upcoming_runners", UPCOMING_MIGRATIONS)
        _migrate_columns(conn, "paper_bets", PAPER_BETS_MIGRATIONS)
        _migrate_columns(conn, "card_scores", CARD_SCORES_MIGRATIONS)
        _migrate_columns(conn, "execution_log", EXECUTION_LOG_MIGRATIONS)
        _migrate_columns(conn, "scored_runner_snapshots", SNAPSHOT_MIGRATIONS)
        for stmt in (
            "CREATE INDEX IF NOT EXISTS idx_upcoming_natural ON upcoming_runners (race_natural_key)",
            "CREATE INDEX IF NOT EXISTS idx_runners_natural ON runners (race_natural_key)",
            "CREATE INDEX IF NOT EXISTS idx_runners_enrich_backfill_lookup ON runners (race_id, runner_id)",
            "CREATE INDEX IF NOT EXISTS idx_runners_race_date ON runners (race_date)",
        ):
            try:
                conn.execute(stmt)
            except sqlite3.OperationalError:
                pass
        conn.commit()
