from __future__ import annotations

import sqlite3
from pathlib import Path

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
)

CARD_SCORES_MIGRATIONS: tuple[tuple[str, str], ...] = (
    ("scoring_method", "TEXT"),
    ("jockey_bayes_place", "REAL"),
    ("trainer_bayes_place", "REAL"),
    ("jockey_place_90d", "REAL"),
    ("trainer_place_90d", "REAL"),
)

RUNNER_NATURAL_MIGRATIONS: tuple[tuple[str, str], ...] = (
    ("off_time", "TEXT"),
    ("race_natural_key", "TEXT"),
)

PAPER_BETS_MIGRATIONS: tuple[tuple[str, str], ...] = (
    ("is_value_pick", "INTEGER NOT NULL DEFAULT 0"),
    ("finish_pos", "INTEGER"),
)


def connect(db: Path) -> sqlite3.Connection:
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


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
        _migrate_columns(conn, "upcoming_runners", UPCOMING_MIGRATIONS)
        _migrate_columns(conn, "paper_bets", PAPER_BETS_MIGRATIONS)
        _migrate_columns(conn, "card_scores", CARD_SCORES_MIGRATIONS)
        for stmt in (
            "CREATE INDEX IF NOT EXISTS idx_upcoming_natural ON upcoming_runners (race_natural_key)",
            "CREATE INDEX IF NOT EXISTS idx_runners_natural ON runners (race_natural_key)",
        ):
            try:
                conn.execute(stmt)
            except sqlite3.OperationalError:
                pass
        conn.commit()
