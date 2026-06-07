from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pandas as pd

from hibs_racing.config import db_path, load_config
from hibs_racing.entity.natural_key import generate_natural_key, normalize_off_time
from hibs_racing.features.store import connect, init_db
from hibs_racing.ingest.csv_loader import utc_now
from hibs_racing.nlp.normalize import normalize_comment

_FRAC_SP_RE = re.compile(r"^(\d+(?:\.\d+)?)/(\d+(?:\.\d+)?)")


def fractional_to_decimal(sp: object) -> float | None:
    if sp is None or (isinstance(sp, float) and pd.isna(sp)):
        return None
    text = str(sp).strip().upper().replace("F", "").replace("J", "").replace("C", "")
    if not text:
        return None
    match = _FRAC_SP_RE.match(text)
    if match:
        num, den = float(match.group(1)), float(match.group(2))
        if den == 0:
            return None
        return 1.0 + num / den
    try:
        val = float(text)
        return val if val > 1.0 else None
    except ValueError:
        return None


def _race_type(value: object) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip().lower()
    if "flat" in text:
        return "flat"
    if any(x in text for x in ("hurdle", "chase", "nh")):
        return "jumps"
    if "aw" in text:
        return "aw"
    return text or None


def load_raceform_frame(
    db_file: Path,
    *,
    since: str | None = None,
    until: str | None = None,
    year: int | None = None,
    limit: int | None = None,
    comments_only: bool = False,
) -> pd.DataFrame:
    """Load runner rows from Kaggle-style raceform.db (`table` holds ~1.8M rows)."""
    if not db_file.exists():
        raise FileNotFoundError(db_file)

    clauses: list[str] = ["pos IS NOT NULL", "pos != ''"]
    params: list[object] = []
    if year:
        clauses.append("date >= ? AND date < ?")
        params.extend([f"{year}-01-01", f"{year + 1}-01-01"])
    if since:
        clauses.append("date >= ?")
        params.append(since)
    if until:
        clauses.append("date <= ?")
        params.append(until)
    if comments_only:
        clauses.append("comment IS NOT NULL AND length(trim(comment)) > 5")

    sql = f"""
        SELECT
            date, course, race_id, off, race_name, type, class, going, ran,
            pos, draw, horse, jockey, trainer, sp, [or], rpr, comment
        FROM [table]
        WHERE {' AND '.join(clauses)}
        ORDER BY date, race_id, num
    """
    if limit:
        sql += f" LIMIT {int(limit)}"

    with sqlite3.connect(db_file) as src:
        return pd.read_sql_query(sql, src, params=params)


def normalize_raceform_frame(frame: pd.DataFrame, *, require_comment: bool = True) -> pd.DataFrame:
    out = pd.DataFrame()
    out["race_id"] = frame["race_id"].astype(str)
    out["race_date"] = pd.to_datetime(frame["date"]).dt.strftime("%Y-%m-%d")
    out["horse_id"] = frame["horse"].astype(str).str.strip()
    out["finish_pos"] = pd.to_numeric(frame["pos"], errors="coerce").astype("Int64")
    out["comment"] = frame["comment"].fillna("").astype(str).str.strip()
    out["course"] = frame["course"]
    out["race_type"] = frame["type"].map(_race_type)
    out["going"] = frame["going"]
    out["field_size"] = pd.to_numeric(frame["ran"], errors="coerce").astype("Int64")
    out["sp_decimal"] = frame["sp"].map(fractional_to_decimal)
    out["jockey"] = frame["jockey"].fillna("").astype(str).str.strip()
    out["trainer"] = frame["trainer"].fillna("").astype(str).str.strip()
    out["draw"] = pd.to_numeric(frame["draw"], errors="coerce").astype("Int64")
    out["official_rating"] = pd.to_numeric(frame["or"], errors="coerce").astype("Int64")
    out["rpr"] = pd.to_numeric(frame["rpr"], errors="coerce").astype("Int64")
    out["race_class"] = frame["class"].fillna("").astype(str).str.strip()
    if "off" in frame.columns:
        out["off_time"] = frame["off"].astype(str).str.strip()
        out["race_natural_key"] = [
            generate_natural_key(str(d)[:10], c, normalize_off_time(t))
            for d, c, t in zip(out["race_date"], out["course"], out["off_time"], strict=False)
        ]

    if require_comment:
        out = out[out["comment"].str.len() > 0].copy()
    out["runner_id"] = (
        out["race_id"].astype(str) + ":" + out["horse_id"].str.lower().str.replace(r"\s+", "_", regex=True)
    )

    out = out.sort_values(["horse_id", "race_date", "race_id"])
    out["race_date_dt"] = pd.to_datetime(out["race_date"])
    out["days_since_last_run"] = (
        out.groupby("horse_id", sort=False)["race_date_dt"].diff().dt.days.astype("Int64")
    )
    out = out.drop(columns=["race_date_dt"])
    return out


def ingest_raceform_db(
    db_file: Path,
    *,
    since: str | None = None,
    until: str | None = None,
    year: int | None = None,
    limit: int | None = None,
    database: Path | None = None,
    batch_size: int = 2000,
    comments_only: bool | None = None,
) -> dict[str, int]:
    """Bulk ingest raceform.db into hibs-racing SQLite."""
    cfg = load_config()
    db = database or db_path(cfg)
    init_db(db)
    require_comment = (
        comments_only
        if comments_only is not None
        else cfg.get("ingest", {}).get("results_require_comment", True)
    )

    frame = load_raceform_frame(
        db_file,
        since=since,
        until=until,
        year=year,
        limit=limit,
        comments_only=bool(require_comment),
    )
    if frame.empty:
        return {"loaded": 0, "inserted": 0}

    norm = normalize_raceform_frame(frame, require_comment=bool(require_comment))
    ingested_at = utc_now()
    source_tag = f"raceform:{db_file.name}"
    inserted = 0

    insert_sql = """
        INSERT INTO runners (
            runner_id, race_id, horse_id, race_date, course, region,
            race_type, going, field_size, finish_pos,
            sp_decimal, jockey, trainer, draw, official_rating, rpr,
            race_class, days_since_last_run, off_time, race_natural_key,
            comment_raw, comment_norm, source_file,
            source_hash, ingested_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(runner_id) DO UPDATE SET
            finish_pos = excluded.finish_pos,
            jockey = excluded.jockey,
            trainer = excluded.trainer,
            draw = excluded.draw,
            official_rating = excluded.official_rating,
            rpr = excluded.rpr,
            race_class = excluded.race_class,
            days_since_last_run = excluded.days_since_last_run,
            off_time = COALESCE(excluded.off_time, off_time),
            race_natural_key = COALESCE(excluded.race_natural_key, race_natural_key),
            comment_raw = CASE WHEN length(excluded.comment_raw) > 0 THEN excluded.comment_raw ELSE comment_raw END,
            comment_norm = CASE WHEN length(excluded.comment_norm) > 0 THEN excluded.comment_norm ELSE comment_norm END,
            ingested_at = excluded.ingested_at
    """

    with connect(db) as conn:
        batch: list[tuple] = []
        for rec in norm.to_dict(orient="records"):
            comment = normalize_comment(rec.get("comment"))
            batch.append(
                (
                    rec["runner_id"],
                    rec["race_id"],
                    rec["horse_id"],
                    rec["race_date"],
                    rec.get("course"),
                    "GB",
                    rec.get("race_type"),
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
                    rec.get("off_time"),
                    rec.get("race_natural_key"),
                    comment.raw,
                    comment.normalized,
                    source_tag,
                    f"{source_tag}:{rec['race_date']}",
                    ingested_at,
                )
            )
            if len(batch) >= batch_size:
                conn.executemany(insert_sql, batch)
                inserted += len(batch)
                batch.clear()
        if batch:
            conn.executemany(insert_sql, batch)
            inserted += len(batch)
        conn.commit()

    return {"loaded": len(frame), "inserted": inserted, "with_comments": len(norm)}
