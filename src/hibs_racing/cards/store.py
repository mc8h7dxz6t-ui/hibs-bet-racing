from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from hibs_racing.cards.enrich import ENRICH_MERGE_COLUMNS
from hibs_racing.config import db_path, load_config
from hibs_racing.entity.natural_key import generate_natural_key
from hibs_racing.features.store import connect, init_db

_STORE_OPTIONAL = (
    "form_string",
    "trainer_rtf",
    "trainer_14d_wins",
    "trainer_14d_runs",
    "trainer_location",
    "rp_verdict",
    "enrich_source",
    "enriched_at",
    "trainer_14d_strike",
    *ENRICH_MERGE_COLUMNS,
)


def _val(rec: dict, key: str):
    v = rec.get(key)
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    return v


def _int_val(rec: dict, key: str) -> int | None:
    v = _val(rec, key)
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _float_val(rec: dict, key: str) -> float | None:
    v = _val(rec, key)
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def store_upcoming_runners(frame: pd.DataFrame, *, source: str, database: Path | None = None) -> int:
    init_db(database or db_path(load_config()))
    db = database or db_path(load_config())
    from hibs_racing.cards.dq_persist import merge_runners_preserve_best, preserve_best_dq_enabled

    if preserve_best_dq_enabled():
        existing = load_upcoming_runners(database=db)
        if not existing.empty:
            frame = merge_runners_preserve_best(existing, frame)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    count = 0
    with connect(db) as conn:
        conn.execute("DELETE FROM upcoming_runners")
        for rec in frame.to_dict(orient="records"):
            natural_key = generate_natural_key(
                str(rec["card_date"]),
                rec.get("course"),
                rec.get("off_time"),
            )
            optional = {k: rec.get(k) for k in _STORE_OPTIONAL if k in rec or k in ENRICH_MERGE_COLUMNS}
            conn.execute(
                """
                INSERT INTO upcoming_runners (
                    runner_id, race_id, card_date, off_time, course, region,
                    race_name, race_type, race_class, going, field_size, distance_f,
                    horse_id, horse_name, draw, official_rating, rpr,
                    jockey, trainer, days_since_last_run, card_comment, rp_verdict, win_decimal,
                    form_string, trainer_rtf, trainer_14d_wins, trainer_14d_runs, trainer_location,
                    horse_course_wins, horse_course_runs, horse_course_win_rate,
                    horse_distance_wins, horse_distance_runs, horse_distance_win_rate,
                    horse_going_wins, horse_going_runs, horse_going_win_rate,
                    jockey_rp_14d_wins, jockey_rp_14d_runs, jockey_rp_14d_win_rate, jockey_rp_14d_wins_pct,
                    trainer_rp_14d_wins, trainer_rp_14d_runs, trainer_rp_14d_win_rate, trainer_rp_14d_wins_pct,
                    form_lto_position, form_trip_change_f, form_cd_flag, form_bf_flag, form_poor_runs_3,
                    trainer_14d_strike, enrich_source, enriched_at,
                    race_natural_key, source, fetched_at
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?, ?, ?, ?,
                    ?, ?, ?,
                    ?, ?, ?
                )
                """,
                (
                    rec["runner_id"],
                    rec["race_id"],
                    rec["card_date"],
                    rec.get("off_time"),
                    rec.get("course"),
                    rec.get("region"),
                    rec.get("race_name"),
                    rec.get("race_type"),
                    rec.get("race_class"),
                    rec.get("going"),
                    _int_val(rec, "field_size"),
                    _float_val(rec, "distance_f"),
                    str(rec["horse_id"]),
                    rec.get("horse_name"),
                    _int_val(rec, "draw"),
                    _int_val(rec, "official_rating"),
                    _int_val(rec, "rpr"),
                    rec.get("jockey"),
                    rec.get("trainer"),
                    _int_val(rec, "days_since_last_run"),
                    rec.get("card_comment"),
                    rec.get("rp_verdict"),
                    _float_val(rec, "win_decimal"),
                    optional.get("form_string"),
                    _float_val(rec, "trainer_rtf"),
                    _int_val(rec, "trainer_14d_wins"),
                    _int_val(rec, "trainer_14d_runs"),
                    optional.get("trainer_location"),
                    _int_val(rec, "horse_course_wins"),
                    _int_val(rec, "horse_course_runs"),
                    _float_val(rec, "horse_course_win_rate"),
                    _int_val(rec, "horse_distance_wins"),
                    _int_val(rec, "horse_distance_runs"),
                    _float_val(rec, "horse_distance_win_rate"),
                    _int_val(rec, "horse_going_wins"),
                    _int_val(rec, "horse_going_runs"),
                    _float_val(rec, "horse_going_win_rate"),
                    _int_val(rec, "jockey_rp_14d_wins"),
                    _int_val(rec, "jockey_rp_14d_runs"),
                    _float_val(rec, "jockey_rp_14d_win_rate"),
                    _float_val(rec, "jockey_rp_14d_wins_pct"),
                    _int_val(rec, "trainer_rp_14d_wins"),
                    _int_val(rec, "trainer_rp_14d_runs"),
                    _float_val(rec, "trainer_rp_14d_win_rate"),
                    _float_val(rec, "trainer_rp_14d_wins_pct"),
                    _int_val(rec, "form_lto_position"),
                    _float_val(rec, "form_trip_change_f"),
                    _int_val(rec, "form_cd_flag"),
                    _int_val(rec, "form_bf_flag"),
                    _int_val(rec, "form_poor_runs_3"),
                    _float_val(rec, "trainer_14d_strike"),
                    optional.get("enrich_source"),
                    optional.get("enriched_at"),
                    natural_key,
                    source,
                    now,
                ),
            )
            count += 1
        conn.commit()
    return count


def load_upcoming_runners(database: Path | None = None) -> pd.DataFrame:
    db = database or db_path(load_config())
    init_db(db)
    with connect(db) as conn:
        return pd.read_sql_query("SELECT * FROM upcoming_runners", conn)
