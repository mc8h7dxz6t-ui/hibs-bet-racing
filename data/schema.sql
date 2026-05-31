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
