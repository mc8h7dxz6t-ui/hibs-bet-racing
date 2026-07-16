-- hibs-racing feature store (Phase A). Separate from hibs-bet football.

CREATE TABLE IF NOT EXISTS runners (
    runner_id       TEXT PRIMARY KEY,
    race_id         TEXT NOT NULL,
    horse_id        TEXT,
    race_date       TEXT NOT NULL,
    course          TEXT,
    region          TEXT,
    race_type       TEXT,          -- flat | jumps | aw
    distance_f      REAL,
    going           TEXT,
    field_size      INTEGER,
    finish_pos      INTEGER,
    sp_decimal      REAL,
    jockey          TEXT,
    trainer         TEXT,
    draw            INTEGER,
    official_rating INTEGER,
    rpr             INTEGER,
    race_class      TEXT,
    days_since_last_run INTEGER,
    off_time        TEXT,
    race_natural_key TEXT,
    comment_raw     TEXT,
    comment_norm    TEXT,
    source_file     TEXT,
    source_hash     TEXT,
    ingested_at     TEXT NOT NULL,
    UNIQUE (race_id, horse_id)
);

CREATE INDEX IF NOT EXISTS idx_runners_date ON runners (race_date);
CREATE INDEX IF NOT EXISTS idx_runners_horse ON runners (horse_id, race_date);
CREATE INDEX IF NOT EXISTS idx_runners_type ON runners (race_type);

CREATE TABLE IF NOT EXISTS comment_tags (
    runner_id               TEXT PRIMARY KEY REFERENCES runners(runner_id),
    late_pace_acceleration  REAL NOT NULL DEFAULT 0,
    finishing_burst         REAL NOT NULL DEFAULT 0,
    stamina_deficit         REAL NOT NULL DEFAULT 0,
    trouble_in_running      REAL NOT NULL DEFAULT 0,
    prominent_early         REAL NOT NULL DEFAULT 0,
    held_up                 REAL NOT NULL DEFAULT 0,
    late_pace_level         INTEGER NOT NULL DEFAULT 0,
    finishing_burst_level   INTEGER NOT NULL DEFAULT 0,
    stamina_deficit_flag    INTEGER NOT NULL DEFAULT 0,
    headway_at_furlongs     REAL,
    fade_in_final_furlong   INTEGER NOT NULL DEFAULT 0,
    quickened_to_lead       INTEGER NOT NULL DEFAULT 0,
    sectional_composite     REAL NOT NULL DEFAULT 0,
    parser_backend          TEXT NOT NULL DEFAULT 'regex',
    tag_count               INTEGER NOT NULL DEFAULT 0,
    tagged_at               TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS next_run_outcomes (
    runner_id       TEXT PRIMARY KEY REFERENCES runners(runner_id),
    next_race_id    TEXT,
    next_race_date  TEXT,
    next_finish_pos INTEGER,
    next_placed     INTEGER,       -- 1 if finish <= place_cutoff
    place_cutoff    INTEGER,
    tagged_at       TEXT NOT NULL
);

-- Phase B: paper ledger (no live stakes)
CREATE TABLE IF NOT EXISTS paper_bets (
    bet_id          TEXT PRIMARY KEY,
    race_id         TEXT NOT NULL,
    runner_id       TEXT NOT NULL,
    bet_type        TEXT NOT NULL,  -- win | place | each_way
    stake_units     REAL NOT NULL,
    model_ev        REAL,
    offered_win     REAL,
    offered_place   REAL,
    place_terms     TEXT,           -- e.g. 1/4 top 3
    status          TEXT NOT NULL DEFAULT 'open',
    result_pnl      REAL,
    settled_at      TEXT,
    is_value_pick   INTEGER NOT NULL DEFAULT 0,
    finish_pos      INTEGER,
    closing_sp      REAL,
    clv_beat        INTEGER,
    verification_hash TEXT,
    backtest         INTEGER NOT NULL DEFAULT 0,
    created_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ingest_log (
    source_hash     TEXT PRIMARY KEY,
    source_file     TEXT NOT NULL,
    row_count       INTEGER NOT NULL,
    ingested_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ranker_features (
    runner_id               TEXT PRIMARY KEY REFERENCES runners(runner_id),
    race_id                 TEXT NOT NULL,
    combo_prior_rides       INTEGER NOT NULL DEFAULT 0,
    combo_bayes_win         REAL,
    combo_bayes_place       REAL,
    hidden_potential        REAL NOT NULL DEFAULT 0,
    or_vs_field             REAL,
    rpr_vs_field            REAL,
    nlp_pace_vs_field       REAL,
    nlp_pace_rank           REAL,
    combo_vs_field          REAL,
    draw_bias_z             REAL,
    finish_pos              INTEGER,
    won                     INTEGER,
    placed                  INTEGER,
    built_at                TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ranker_race ON ranker_features (race_id);

CREATE TABLE IF NOT EXISTS upcoming_runners (
    runner_id       TEXT PRIMARY KEY,
    race_id         TEXT NOT NULL,
    card_date       TEXT NOT NULL,
    off_time        TEXT,
    course          TEXT,
    region          TEXT,
    race_name       TEXT,
    race_type       TEXT,
    race_class      TEXT,
    going           TEXT,
    field_size      INTEGER,
    distance_f      REAL,
    place_fraction  REAL,
    places          INTEGER,
    offered_place_decimal REAL,
    horse_id        TEXT NOT NULL,
    horse_name      TEXT,
    draw            INTEGER,
    official_rating INTEGER,
    rpr             INTEGER,
    jockey          TEXT,
    trainer         TEXT,
    days_since_last_run INTEGER,
    card_comment    TEXT,
    rp_verdict      TEXT,
    win_decimal     REAL,
    race_natural_key TEXT,
    source          TEXT NOT NULL,
    fetched_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_upcoming_race ON upcoming_runners (race_id);
CREATE INDEX IF NOT EXISTS idx_upcoming_date ON upcoming_runners (card_date);

CREATE TABLE IF NOT EXISTS card_scores (
    runner_id           TEXT PRIMARY KEY,
    race_id             TEXT NOT NULL,
    model_score         REAL NOT NULL,
    model_win_prob      REAL,
    model_place_prob    REAL,
    combo_bayes_place   REAL,
    hidden_potential    REAL,
    nlp_pace_rank       REAL,
    place_ev            REAL,
    ew_combined_ev      REAL,
    value_flag          INTEGER NOT NULL DEFAULT 0,
    scoring_method      TEXT,
    scored_at           TEXT NOT NULL
);

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

-- Phase C: execution audit log (routing instructions + live dedup)
CREATE TABLE IF NOT EXISTS execution_log (
    log_id                      TEXT PRIMARY KEY,
    batch_id                    TEXT NOT NULL,
    runner_id                   TEXT NOT NULL,
    race_id                     TEXT NOT NULL,
    horse_name                  TEXT,
    course                      TEXT,
    off_time                    TEXT,
    bet_type                    TEXT NOT NULL,   -- win | place | each_way
    bet_leg                     TEXT NOT NULL,   -- win | place (exchange leg)
    venue                       TEXT NOT NULL,   -- matchbook | betfair | none
    status                      TEXT NOT NULL,   -- routed | rejected | stub_ok | stub_error | skipped_duplicate
    dry_run                     INTEGER NOT NULL DEFAULT 1,
    stake                       REAL,
    odds                        REAL,
    place_odds                  REAL,
    steam_gate                  TEXT,
    value_flag                  INTEGER NOT NULL DEFAULT 0,
    kelly_multiplier            REAL,
    message                     TEXT,
    external_id                 TEXT,
    matchbook_runner_id         INTEGER,
    matchbook_market_id         INTEGER,
    matchbook_place_market_id   INTEGER,
    matchbook_event_id          INTEGER,
    betfair_market_id           TEXT,
    betfair_selection_id        INTEGER,
    betfair_place_market_id     TEXT,
    payload_json                TEXT,
    idempotency_key             TEXT NOT NULL,
    created_at                  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_execution_log_batch ON execution_log (batch_id);
CREATE INDEX IF NOT EXISTS idx_execution_log_runner ON execution_log (runner_id, created_at);
CREATE INDEX IF NOT EXISTS idx_execution_log_created ON execution_log (created_at);

-- One live routed offer per runner/leg/venue (re-runs skip instead of double-bet)
CREATE UNIQUE INDEX IF NOT EXISTS idx_execution_log_live_dedup
ON execution_log (idempotency_key)
WHERE dry_run = 0 AND status = 'routed';

-- Phase D: immutable scored-card snapshots for fast gate replay / audit
CREATE TABLE IF NOT EXISTS scored_runner_snapshots (
    card_date               TEXT NOT NULL,
    runner_id               TEXT NOT NULL,
    race_id                 TEXT NOT NULL,
    odds_source             TEXT NOT NULL DEFAULT 'sp',
    config_hash             TEXT NOT NULL,
    course                  TEXT,
    race_name               TEXT,
    field_size              INTEGER,
    official_rating         INTEGER,
    win_decimal             REAL,
    place_fraction          REAL,
    places                  INTEGER,
    model_score             REAL,
    model_win_prob          REAL,
    model_place_prob        REAL,
    combo_bayes_place       REAL,
    place_ev                REAL,
    ew_combined_ev          REAL,
    flag_raw                INTEGER NOT NULL DEFAULT 0,
    finish_pos              INTEGER,
    scored_at               TEXT NOT NULL,
    manifest_json           TEXT,
    gates_json              TEXT,
    PRIMARY KEY (card_date, runner_id, odds_source, config_hash)
);

CREATE INDEX IF NOT EXISTS idx_snapshots_date ON scored_runner_snapshots (card_date);
CREATE INDEX IF NOT EXISTS idx_snapshots_config ON scored_runner_snapshots (config_hash);

-- Phase E: institutional run manifests + append-only ledger events
CREATE TABLE IF NOT EXISTS run_manifests (
    manifest_id         TEXT PRIMARY KEY,
    manifest_hash         TEXT NOT NULL,
    run_kind              TEXT NOT NULL,
    card_date             TEXT,
    config_hash           TEXT NOT NULL,
    model_version         TEXT NOT NULL,
    scoring_method        TEXT,
    git_sha               TEXT,
    odds_source           TEXT,
    runner_count          INTEGER NOT NULL DEFAULT 0,
    value_flag_count      INTEGER NOT NULL DEFAULT 0,
    extras_json           TEXT,
    created_at            TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_run_manifests_date ON run_manifests (card_date, created_at);

CREATE TABLE IF NOT EXISTS ledger_events (
    event_id              TEXT PRIMARY KEY,
    event_type            TEXT NOT NULL,
    runner_id             TEXT,
    race_id               TEXT,
    payload_json          TEXT NOT NULL,
    manifest_id           TEXT,
    verification_hash     TEXT,
    created_at            TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ledger_events_type ON ledger_events (event_type, created_at);
CREATE INDEX IF NOT EXISTS idx_ledger_events_manifest ON ledger_events (manifest_id);

-- Exchange order-book snapshots (Matchbook back/lay + top-of-book liquidity)
CREATE TABLE IF NOT EXISTS exchange_quotes (
    runner_id               TEXT NOT NULL,
    timestamp               TEXT NOT NULL,
    odds_source             TEXT NOT NULL DEFAULT 'matchbook',
    poll_milestone          TEXT NOT NULL DEFAULT 'intraday',
    card_date               TEXT,
    race_id                 TEXT,
    back_price              REAL,
    back_liquidity          REAL,
    lay_price               REAL,
    lay_liquidity           REAL,
    exchange_spread_bps     REAL,
    PRIMARY KEY (runner_id, timestamp)
);

CREATE INDEX IF NOT EXISTS idx_exchange_quotes_date ON exchange_quotes (card_date, poll_milestone);
CREATE INDEX IF NOT EXISTS idx_exchange_quotes_runner ON exchange_quotes (runner_id, poll_milestone, timestamp);

-- Post-race SP join for value picks (baseline / pre-race quotes vs official SP)
CREATE TABLE IF NOT EXISTS value_pick_execution (
    runner_id               TEXT NOT NULL,
    card_date               TEXT NOT NULL,
    race_id                 TEXT,
    baseline_back           REAL,
    baseline_ts             TEXT,
    pre_race_30m_back       REAL,
    pre_race_30m_ts         TEXT,
    closing_sp              REAL,
    sp_captured_at          TEXT,
    slippage_bps            REAL,
    spread_bps_at_baseline  REAL,
    liquidity_at_baseline   REAL,
    PRIMARY KEY (runner_id, card_date)
);

CREATE INDEX IF NOT EXISTS idx_value_pick_exec_date ON value_pick_execution (card_date);

-- McFadden conditional logit win engine (isolated from paper_bets / trade_evidence)
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

-- Event-driven trading engine (sandboxed — HIBS_LIVE_TRADING_ENABLED=false default)
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
