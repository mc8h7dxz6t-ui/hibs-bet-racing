-- Historical training parity: align `runners` enrich spine with `upcoming_runners`.
-- Applied automatically via init_db() RUNNER_ENRICH_MIGRATIONS; kept here for ops audit.

ALTER TABLE runners ADD COLUMN form_string TEXT;
ALTER TABLE runners ADD COLUMN trainer_14d_wins INTEGER;
ALTER TABLE runners ADD COLUMN trainer_14d_runs INTEGER;
ALTER TABLE runners ADD COLUMN horse_course_win_rate REAL;
ALTER TABLE runners ADD COLUMN horse_distance_win_rate REAL;
ALTER TABLE runners ADD COLUMN horse_going_win_rate REAL;
ALTER TABLE runners ADD COLUMN jockey_rp_14d_win_rate REAL;
ALTER TABLE runners ADD COLUMN trainer_rp_14d_win_rate REAL;
ALTER TABLE runners ADD COLUMN trainer_rtf REAL;
ALTER TABLE runners ADD COLUMN trainer_14d_strike REAL;
ALTER TABLE runners ADD COLUMN form_lto_position INTEGER;
ALTER TABLE runners ADD COLUMN form_trip_change_f REAL;
ALTER TABLE runners ADD COLUMN form_cd_flag INTEGER;
ALTER TABLE runners ADD COLUMN form_bf_flag INTEGER;
ALTER TABLE runners ADD COLUMN form_poor_runs_3 INTEGER;
ALTER TABLE runners ADD COLUMN enrich_source TEXT;
ALTER TABLE runners ADD COLUMN enriched_at TEXT;

CREATE INDEX IF NOT EXISTS idx_runners_enrich_backfill_lookup ON runners (race_id, runner_id);
CREATE INDEX IF NOT EXISTS idx_runners_race_date ON runners (race_date);
