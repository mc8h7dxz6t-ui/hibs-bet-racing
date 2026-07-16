-- McFadden conditional logit win engine — isolated from paper_bets / trade_evidence.
-- Applied via init_db() WIN_ENGINE_DDL; kept here for ops audit.
-- Field-calibration columns: migrations/008_win_engine_field_calibration.sql

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

INSERT OR IGNORE INTO win_engine_calibration (id, calibration_state, updated_at)
VALUES (1, 'UNCALIBRATED', datetime('now'));
