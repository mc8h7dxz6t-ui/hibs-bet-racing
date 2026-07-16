-- Liquidity router tables (routing_decisions + hedged_ledger_events)
-- Applied idempotently via init_db() and ensure_trading_schema().

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
