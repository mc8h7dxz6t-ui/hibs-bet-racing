from __future__ import annotations

from pathlib import Path

import pandas as pd

from hibs_racing.config import db_path, load_config
from hibs_racing.features.store import connect, init_db
from hibs_racing.ingest.csv_loader import file_hash, normalize_csv_frame, utc_now
from hibs_racing.nlp.normalize import normalize_comment


def _days_since_last_run(frame: pd.DataFrame) -> pd.Series:
    tmp = frame.sort_values(["horse_id", "race_date"]).copy()
    tmp["race_date_dt"] = pd.to_datetime(tmp["race_date"])
    tmp["days_since_last_run"] = tmp.groupby("horse_id", sort=False)["race_date_dt"].diff().dt.days
    lookup = tmp.set_index("runner_id")["days_since_last_run"]
    return frame["runner_id"].map(lookup)


def ingest_csv(
    csv_path: Path,
    *,
    config_path: Path | None = None,
    database: Path | None = None,
    skip_if_seen: bool = True,
) -> int:
    """Idempotent ingest: one row per runner. Returns rows inserted/updated."""
    cfg = load_config(config_path)
    db = database or db_path(cfg)
    init_db(db)

    source_hash = file_hash(csv_path)
    with connect(db) as conn:
        if skip_if_seen:
            row = conn.execute(
                "SELECT 1 FROM ingest_log WHERE source_hash = ?", (source_hash,)
            ).fetchone()
            if row:
                return 0

    frame = normalize_csv_frame(pd.read_csv(csv_path))
    if "days_since_last_run" not in frame.columns:
        frame["days_since_last_run"] = _days_since_last_run(frame).astype("Int64")

    ingested_at = utc_now()
    rows = 0

    with connect(db) as conn:
        for rec in frame.to_dict(orient="records"):
            norm = normalize_comment(rec.get("comment"))
            conn.execute(
                """
                INSERT INTO runners (
                    runner_id, race_id, horse_id, race_date, course, region,
                    race_type, distance_f, going, field_size, finish_pos,
                    sp_decimal, jockey, trainer, draw, official_rating, rpr,
                    race_class, days_since_last_run,
                    comment_raw, comment_norm, source_file,
                    source_hash, ingested_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(runner_id) DO UPDATE SET
                    finish_pos = excluded.finish_pos,
                    jockey = excluded.jockey,
                    trainer = excluded.trainer,
                    draw = excluded.draw,
                    official_rating = excluded.official_rating,
                    rpr = excluded.rpr,
                    race_class = excluded.race_class,
                    days_since_last_run = excluded.days_since_last_run,
                    comment_raw = excluded.comment_raw,
                    comment_norm = excluded.comment_norm,
                    ingested_at = excluded.ingested_at
                """,
                (
                    rec["runner_id"],
                    rec["race_id"],
                    rec["horse_id"],
                    rec["race_date"],
                    rec.get("course"),
                    rec.get("region"),
                    rec.get("race_type"),
                    rec.get("distance_f"),
                    rec.get("going"),
                    int(rec["field_size"]) if pd.notna(rec.get("field_size")) else None,
                    int(rec["finish_pos"]) if pd.notna(rec.get("finish_pos")) else None,
                    rec.get("sp_decimal"),
                    rec.get("jockey"),
                    rec.get("trainer"),
                    int(rec["draw"]) if pd.notna(rec.get("draw")) else None,
                    int(rec["official_rating"]) if pd.notna(rec.get("official_rating")) else None,
                    int(rec["rpr"]) if pd.notna(rec.get("rpr")) else None,
                    rec.get("race_class"),
                    int(rec["days_since_last_run"]) if pd.notna(rec.get("days_since_last_run")) else None,
                    norm.raw,
                    norm.normalized,
                    str(csv_path.name),
                    source_hash,
                    ingested_at,
                ),
            )
            rows += 1

        conn.execute(
            """
            INSERT INTO ingest_log (source_hash, source_file, row_count, ingested_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(source_hash) DO NOTHING
            """,
            (source_hash, str(csv_path.name), rows, ingested_at),
        )
        conn.commit()

    return rows


def export_parquet_year(
    csv_path: Path,
    *,
    parquet_dir: Path | None = None,
    config_path: Path | None = None,
) -> Path:
    """Normalize CSV → year partition Parquet (cold archive layer)."""
    cfg = load_config(config_path)
    out_dir = parquet_dir or Path(cfg["paths"]["parquet_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)

    frame = normalize_csv_frame(pd.read_csv(csv_path))
    year = frame["race_date"].str[:4].iloc[0]
    target = out_dir / f"runners_{year}.parquet"
    frame.to_parquet(target, index=False)
    return target
