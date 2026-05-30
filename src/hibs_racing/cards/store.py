from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from hibs_racing.config import db_path, load_config
from hibs_racing.entity.natural_key import generate_natural_key
from hibs_racing.features.store import connect, init_db


def store_upcoming_runners(frame: pd.DataFrame, *, source: str, database: Path | None = None) -> int:
    init_db(database or db_path(load_config()))
    db = database or db_path(load_config())
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
            conn.execute(
                """
                INSERT INTO upcoming_runners (
                    runner_id, race_id, card_date, off_time, course, region,
                    race_name, race_type, race_class, going, field_size, distance_f,
                    horse_id, horse_name, draw, official_rating, rpr,
                    jockey, trainer, days_since_last_run, card_comment, win_decimal,
                    form_string, trainer_rtf, trainer_14d_wins, trainer_14d_runs, trainer_location,
                    race_natural_key, source, fetched_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    int(rec["field_size"]) if pd.notna(rec.get("field_size")) else None,
                    float(rec["distance_f"]) if pd.notna(rec.get("distance_f")) else None,
                    str(rec["horse_id"]),
                    rec.get("horse_name"),
                    int(rec["draw"]) if pd.notna(rec.get("draw")) else None,
                    int(rec["official_rating"]) if pd.notna(rec.get("official_rating")) else None,
                    int(rec["rpr"]) if pd.notna(rec.get("rpr")) else None,
                    rec.get("jockey"),
                    rec.get("trainer"),
                    int(rec["days_since_last_run"]) if pd.notna(rec.get("days_since_last_run")) else None,
                    rec.get("card_comment"),
                    float(rec["win_decimal"]) if pd.notna(rec.get("win_decimal")) else None,
                    rec.get("form_string"),
                    float(rec["trainer_rtf"]) if pd.notna(rec.get("trainer_rtf")) else None,
                    int(rec["trainer_14d_wins"]) if pd.notna(rec.get("trainer_14d_wins")) else None,
                    int(rec["trainer_14d_runs"]) if pd.notna(rec.get("trainer_14d_runs")) else None,
                    rec.get("trainer_location"),
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
