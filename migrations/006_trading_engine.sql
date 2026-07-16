-- Event-driven trading engine tables (simulated_trades + CAS wallet)
-- Applied idempotently via init_db() and ensure_trading_schema().

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
