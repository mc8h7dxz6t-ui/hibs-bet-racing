-- Variable field-size multiclass Brier calibration + exchange de-vig overlay.
-- Applied via ensure_win_engine_schema() WIN_ENGINE_MIGRATIONS.

ALTER TABLE win_engine_predictions ADD COLUMN matchbook_back_odds REAL;
ALTER TABLE win_engine_predictions ADD COLUMN race_field_brier REAL;
ALTER TABLE win_engine_predictions ADD COLUMN market_race_brier REAL;
ALTER TABLE win_engine_predictions ADD COLUMN field_size INTEGER;

ALTER TABLE win_engine_calibration ADD COLUMN market_brier_rolling REAL;
ALTER TABLE win_engine_calibration ADD COLUMN exchange_beat_delta_bps REAL;
ALTER TABLE win_engine_calibration ADD COLUMN variable_bounds_pass INTEGER NOT NULL DEFAULT 0;
ALTER TABLE win_engine_calibration ADD COLUMN market_beat_pass INTEGER NOT NULL DEFAULT 0;
