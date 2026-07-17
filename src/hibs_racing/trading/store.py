"""SQLite persistence for sandboxed trading engine tables."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hibs_racing.config import db_path, load_config
from hibs_racing.features.store import connect, init_db
from hibs_racing.trading.config import initial_wallet_balance

TRADING_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS trading_wallet_state (
    wallet_id   TEXT PRIMARY KEY,
    version     INTEGER NOT NULL DEFAULT 0,
    balance     REAL NOT NULL,
    reserved    REAL NOT NULL DEFAULT 0,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS simulated_trades (
    trade_id        TEXT PRIMARY KEY,
    payload_hash    TEXT NOT NULL,
    runner_id       TEXT,
    market_id       TEXT,
    odds            REAL,
    stake           REAL,
    status          TEXT NOT NULL,
    reject_reason   TEXT,
    packet_delay_ms REAL,
    slippage_ticks  REAL,
    payload_json    TEXT,
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_simulated_trades_created ON simulated_trades (created_at);
CREATE INDEX IF NOT EXISTS idx_simulated_trades_hash ON simulated_trades (payload_hash);

CREATE TABLE IF NOT EXISTS trading_idempotency (
    payload_hash    TEXT PRIMARY KEY,
    first_seen_at   TEXT NOT NULL,
    last_seen_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS routing_decisions (
    decision_id         TEXT PRIMARY KEY,
    trade_id            TEXT NOT NULL,
    runner_id           TEXT,
    market_id           TEXT,
    chosen_channel      TEXT NOT NULL,
    gross_odds          REAL,
    net_odds            REAL,
    commission_bps      REAL,
    status              TEXT NOT NULL,
    outbound_blocked    INTEGER NOT NULL DEFAULT 1,
    flight_latency_ms   REAL,
    routed_stake        REAL,
    matchbook_back_volume_pre  REAL,
    matchbook_back_volume_post REAL,
    created_at          TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_routing_decisions_trade ON routing_decisions (trade_id);

CREATE TABLE IF NOT EXISTS hedged_ledger_events (
    event_id            TEXT PRIMARY KEY,
    source_trade_id     TEXT NOT NULL,
    runner_id           TEXT,
    market_id           TEXT,
    back_odds           REAL NOT NULL,
    lay_odds            REAL NOT NULL,
    back_stake          REAL NOT NULL,
    lay_stake           REAL NOT NULL,
    hedge_delta_bps     REAL NOT NULL,
    locked_margin_units REAL,
    channel             TEXT,
    status              TEXT NOT NULL,
    created_at          TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_hedged_ledger_trade ON hedged_ledger_events (source_trade_id);
"""


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _seed_wallet_row(conn: sqlite3.Connection) -> None:
    row = conn.execute(
        "SELECT wallet_id FROM trading_wallet_state WHERE wallet_id = ?",
        ("default",),
    ).fetchone()
    if row is None:
        conn.execute(
            """
            INSERT INTO trading_wallet_state (wallet_id, version, balance, reserved, updated_at)
            VALUES (?, 0, ?, 0, ?)
            """,
            ("default", initial_wallet_balance(), _utc_now()),
        )


def apply_trading_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(TRADING_SCHEMA_SQL)
    _migrate_routing_decisions(conn)
    _seed_wallet_row(conn)


def _migrate_routing_decisions(conn: sqlite3.Connection) -> None:
    cols = {str(r[1]) for r in conn.execute("PRAGMA table_info(routing_decisions)").fetchall()}
    for col, ddl in (
        ("flight_latency_ms", "ALTER TABLE routing_decisions ADD COLUMN flight_latency_ms REAL"),
        ("routed_stake", "ALTER TABLE routing_decisions ADD COLUMN routed_stake REAL"),
        ("matchbook_back_volume_pre", "ALTER TABLE routing_decisions ADD COLUMN matchbook_back_volume_pre REAL"),
        ("matchbook_back_volume_post", "ALTER TABLE routing_decisions ADD COLUMN matchbook_back_volume_post REAL"),
    ):
        if col not in cols:
            conn.execute(ddl)


def ensure_trading_schema(database: Path | None = None) -> Path:
    if database is not None:
        db = database
        db.parent.mkdir(parents=True, exist_ok=True)
        with connect(db) as conn:
            apply_trading_schema(conn)
            conn.commit()
        return db
    db = db_path(load_config())
    init_db(db)
    return db


def cas_reserve_capital(
    conn: sqlite3.Connection,
    *,
    wallet_id: str,
    expected_version: int,
    stake: float,
) -> tuple[bool, str, int | None]:
    """
    Compare-and-swap reserve: atomically bump version and reserve stake when balance allows.
  Returns (ok, reason, new_version).
    """
    row = conn.execute(
        "SELECT version, balance, reserved FROM trading_wallet_state WHERE wallet_id = ?",
        (wallet_id,),
    ).fetchone()
    if row is None:
        return False, "wallet_missing", None
    version = int(row["version"])
    balance = float(row["balance"])
    reserved = float(row["reserved"])
    if version != expected_version:
        return False, "version_conflict", version
    free = balance - reserved
    if stake > free:
        return False, "insufficient_capital", version
    new_version = version + 1
    cur = conn.execute(
        """
        UPDATE trading_wallet_state
        SET version = ?, reserved = reserved + ?, updated_at = ?
        WHERE wallet_id = ? AND version = ?
        """,
        (new_version, stake, _utc_now(), wallet_id, expected_version),
    )
    if cur.rowcount != 1:
        return False, "cas_failed", version
    return True, "reserved", new_version


def release_reserved_capital(
    conn: sqlite3.Connection,
    *,
    wallet_id: str,
    stake: float,
) -> None:
    conn.execute(
        """
        UPDATE trading_wallet_state
        SET reserved = MAX(0, reserved - ?), updated_at = ?
        WHERE wallet_id = ?
        """,
        (stake, _utc_now(), wallet_id),
    )


def get_wallet_state(conn: sqlite3.Connection, *, wallet_id: str = "default") -> dict[str, Any]:
    row = conn.execute(
        "SELECT wallet_id, version, balance, reserved, updated_at FROM trading_wallet_state WHERE wallet_id = ?",
        (wallet_id,),
    ).fetchone()
    if row is None:
        return {}
    return dict(row)


def record_idempotency_hit(conn: sqlite3.Connection, payload_hash: str, *, now: str | None = None) -> bool:
    """Insert or refresh idempotency row. Returns True if duplicate within active window."""
    ts = now or _utc_now()
    row = conn.execute(
        "SELECT payload_hash FROM trading_idempotency WHERE payload_hash = ?",
        (payload_hash,),
    ).fetchone()
    if row:
        conn.execute(
            "UPDATE trading_idempotency SET last_seen_at = ? WHERE payload_hash = ?",
            (ts, payload_hash),
        )
        return True
    conn.execute(
        "INSERT INTO trading_idempotency (payload_hash, first_seen_at, last_seen_at) VALUES (?, ?, ?)",
        (payload_hash, ts, ts),
    )
    return False


def record_simulated_trade(
    conn: sqlite3.Connection,
    *,
    payload_hash: str,
    runner_id: str | None,
    market_id: str | None,
    odds: float | None,
    stake: float | None,
    status: str,
    reject_reason: str | None = None,
    packet_delay_ms: float | None = None,
    slippage_ticks: float | None = None,
    payload: dict[str, Any] | None = None,
) -> str:
    trade_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO simulated_trades (
            trade_id, payload_hash, runner_id, market_id, odds, stake, status,
            reject_reason, packet_delay_ms, slippage_ticks, payload_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            trade_id,
            payload_hash,
            runner_id,
            market_id,
            odds,
            stake,
            status,
            reject_reason,
            packet_delay_ms,
            slippage_ticks,
            json.dumps(payload, sort_keys=True, default=str) if payload else None,
            _utc_now(),
        ),
    )
    return trade_id


def recent_simulated_trades(
    database: Path | None = None,
    *,
    limit: int = 50,
) -> list[dict[str, Any]]:
    db = ensure_trading_schema(database)
    with connect(db) as conn:
        rows = conn.execute(
            "SELECT * FROM simulated_trades ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]
