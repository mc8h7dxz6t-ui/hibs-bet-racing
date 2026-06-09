"""Repair dense gate fields from RP racecard payloads."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from hibs_racing.config import db_path, load_config
from hibs_racing.entity.natural_key import normalize_course
from hibs_racing.features.store import connect, init_db
from hibs_racing.ingest.racecards import RPSCRAPE_RACECARDS, parse_racecard_json
from hibs_racing.odds.matching import normalize_horse_name


def _date_range(start: str, end: str) -> list[str]:
    current = datetime.strptime(start, "%Y-%m-%d").date()
    stop = datetime.strptime(end, "%Y-%m-%d").date()
    out: list[str] = []
    while current <= stop:
        out.append(current.isoformat())
        current += timedelta(days=1)
    return out


def _join_key(frame: pd.DataFrame) -> pd.Series:
    work = frame.copy()
    if "card_date" not in work.columns and "race_date" in work.columns:
        work["card_date"] = work["race_date"]
    name_col = "horse_name" if "horse_name" in work.columns else "horse_id"
    return (
        work["card_date"].astype(str).str[:10]
        + "|"
        + work["course"].map(lambda c: normalize_course(c) or "")
        + "|"
        + work[name_col].map(lambda h: normalize_horse_name(h))
    )


def _int_or_none(raw: Any) -> int | None:
    if raw is None:
        return None
    try:
        if pd.isna(raw):
            return None
    except (TypeError, ValueError):
        pass
    try:
        return int(float(str(raw).strip()))
    except (TypeError, ValueError):
        return None


def _float_or_none(raw: Any) -> float | None:
    if raw is None:
        return None
    try:
        if pd.isna(raw):
            return None
    except (TypeError, ValueError):
        pass
    text = str(raw).strip().replace("%", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def dense_field_coverage(db: Path, *, start: str, end: str) -> dict[str, Any]:
    init_db(db)
    with connect(db) as conn:
        total = conn.execute(
            """
            SELECT COUNT(*)
            FROM runners
            WHERE finish_pos IS NOT NULL
              AND race_date >= ? AND race_date <= ?
            """,
            (start, end),
        ).fetchone()[0]
        official_rating = conn.execute(
            """
            SELECT COUNT(*)
            FROM runners
            WHERE finish_pos IS NOT NULL
              AND race_date >= ? AND race_date <= ?
              AND official_rating IS NOT NULL
            """,
            (start, end),
        ).fetchone()[0]
        trainer_rtf = conn.execute(
            """
            SELECT COUNT(*)
            FROM runners
            WHERE finish_pos IS NOT NULL
              AND race_date >= ? AND race_date <= ?
              AND trainer_rtf IS NOT NULL
            """,
            (start, end),
        ).fetchone()[0]
    return {
        "finished_runners": int(total),
        "official_rating_present_pct": round(100.0 * official_rating / total, 2) if total else 0.0,
        "trainer_rtf_present_pct": round(100.0 * trainer_rtf / total, 2) if total else 0.0,
        "official_rating_missing": int(total - official_rating),
        "trainer_rtf_missing": int(total - trainer_rtf),
    }


def repair_dense_fields_for_date(
    card_date: str,
    *,
    database: Path | None = None,
    racecards_dir: Path | None = None,
    refill: bool = False,
) -> dict[str, Any]:
    """Fill missing official_rating and trainer_rtf from one cached RP racecard JSON."""
    db = database or db_path(load_config())
    cards_dir = racecards_dir or RPSCRAPE_RACECARDS
    json_path = cards_dir / f"{card_date}.json"
    if not json_path.exists():
        return {
            "card_date": card_date,
            "json_path": str(json_path),
            "rows_matched": 0,
            "official_rating_updated": 0,
            "trainer_rtf_updated": 0,
            "message": "No cached RP racecard JSON for dense field repair.",
        }

    try:
        card = parse_racecard_json(json_path)
    except (OSError, ValueError) as exc:
        return {
            "card_date": card_date,
            "json_path": str(json_path),
            "rows_matched": 0,
            "official_rating_updated": 0,
            "trainer_rtf_updated": 0,
            "error": str(exc),
        }
    if card.empty:
        return {
            "card_date": card_date,
            "json_path": str(json_path),
            "rows_matched": 0,
            "official_rating_updated": 0,
            "trainer_rtf_updated": 0,
        }

    card = card.copy()
    card["_dense_key"] = _join_key(card)
    card = card.drop_duplicates(subset=["_dense_key"], keep="last").set_index("_dense_key", drop=False)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    matched = 0
    or_updates = 0
    rtf_updates = 0

    init_db(db)
    with connect(db) as conn:
        runners = pd.read_sql_query(
            """
            SELECT runner_id, race_date, course, horse_id, official_rating, trainer_rtf
            FROM runners
            WHERE finish_pos IS NOT NULL AND race_date = ?
            """,
            conn,
            params=(card_date,),
        )
        if runners.empty:
            return {
                "card_date": card_date,
                "json_path": str(json_path),
                "rows_matched": 0,
                "official_rating_updated": 0,
                "trainer_rtf_updated": 0,
                "message": "No finished runners for date.",
            }
        runners["card_date"] = runners["race_date"]
        runners["_dense_key"] = _join_key(runners)

        for _, row in runners.iterrows():
            key = row["_dense_key"]
            if key not in card.index:
                continue
            src = card.loc[key]
            if isinstance(src, pd.DataFrame):
                src = src.iloc[-1]
            matched += 1
            official_rating = _int_or_none(src.get("official_rating"))
            trainer_rtf = _float_or_none(src.get("trainer_rtf"))
            sets: list[str] = []
            vals: list[Any] = []
            if official_rating is not None and (refill or pd.isna(row.get("official_rating"))):
                sets.append("official_rating = ?")
                vals.append(official_rating)
                or_updates += 1
            if trainer_rtf is not None and (refill or pd.isna(row.get("trainer_rtf"))):
                sets.append("trainer_rtf = ?")
                vals.append(trainer_rtf)
                rtf_updates += 1
            if not sets:
                continue
            sets.extend(["enrich_source = COALESCE(enrich_source, ?)", "enriched_at = ?"])
            vals.extend(["rp_dense_field_repair", now, row["runner_id"]])
            conn.execute(
                f"UPDATE runners SET {', '.join(sets)} WHERE runner_id = ?",
                vals,
            )
        conn.commit()

    return {
        "card_date": card_date,
        "json_path": str(json_path),
        "rows_matched": matched,
        "official_rating_updated": or_updates,
        "trainer_rtf_updated": rtf_updates,
        "rows_updated": or_updates + rtf_updates,
    }


def run_dense_field_repair(
    *,
    start: str,
    end: str,
    database: Path | None = None,
    racecards_dir: Path | None = None,
    fetch_missing: bool = False,
    refill: bool = False,
    max_days: int | None = None,
) -> dict[str, Any]:
    """Repair official_rating/trainer_rtf across a date window from RP racecards."""
    db = database or db_path(load_config())
    cards_dir = racecards_dir or RPSCRAPE_RACECARDS
    before = dense_field_coverage(db, start=start, end=end)
    days = _date_range(start, end)
    if max_days is not None:
        days = days[:max_days]

    day_log: list[dict[str, Any]] = []
    fetched = 0
    for card_date in days:
        json_path = cards_dir / f"{card_date}.json"
        if fetch_missing and not json_path.exists():
            try:
                from hibs_racing.ingest.historical_racecards import fetch_historical_racecards_on_date

                fetch_historical_racecards_on_date(card_date)
                fetched += 1
            except Exception as exc:
                day_log.append({"card_date": card_date, "fetched": False, "error": str(exc)})
                continue
        day_log.append(
            repair_dense_fields_for_date(
                card_date,
                database=db,
                racecards_dir=cards_dir,
                refill=refill,
            )
        )

    after = dense_field_coverage(db, start=start, end=end)
    official_rating_updated = sum(int(d.get("official_rating_updated", 0)) for d in day_log)
    trainer_rtf_updated = sum(int(d.get("trainer_rtf_updated", 0)) for d in day_log)
    return {
        "start": start,
        "end": end,
        "days_processed": len(days),
        "days_fetched": fetched,
        "official_rating_updated": official_rating_updated,
        "trainer_rtf_updated": trainer_rtf_updated,
        "rows_updated": official_rating_updated + trainer_rtf_updated,
        "before": before,
        "after": after,
        "day_log": day_log[-30:],
        "message": (
            f"Dense field repair updated {official_rating_updated} official_rating values and "
            f"{trainer_rtf_updated} trainer_rtf values."
        ),
    }
