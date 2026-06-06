"""Backfill historical runner enrich columns from live caches and RP racecard JSON."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from hibs_racing.cards.enrich import ENRICH_RANKER_FEATURES, compute_enrich_ranker_fields, enrich_join_key
from hibs_racing.config import ROOT, db_path, load_config
from hibs_racing.entity.natural_key import normalize_course
from hibs_racing.features.store import connect, init_db
from hibs_racing.ingest.racecards import RPSCRAPE_RACECARDS, parse_racecard_json
from hibs_racing.odds.matching import normalize_horse_name

_BACKFILL_COLUMNS: tuple[str, ...] = (
    "form_string",
    "trainer_14d_wins",
    "trainer_14d_runs",
    "trainer_14d_strike",
    *ENRICH_RANKER_FEATURES,
)


def _historical_join_key(frame: pd.DataFrame) -> pd.Series:
    work = frame.copy()
    if "card_date" not in work.columns and "race_date" in work.columns:
        work["card_date"] = work["race_date"]
    if "horse_name" not in work.columns:
        work["horse_name"] = work.get("horse_id", pd.Series("", index=work.index))
    return enrich_join_key(work)


def _historical_join_key_loose(frame: pd.DataFrame) -> pd.Series:
    """Fallback when historical runners lack off_time (99%+ of raceform rows)."""
    work = frame.copy()
    if "card_date" not in work.columns and "race_date" in work.columns:
        work["card_date"] = work["race_date"].astype(str).str[:10]
    name_col = "horse_name" if "horse_name" in work.columns else "horse_id"
    return (
        work["card_date"].astype(str).str[:10]
        + "|"
        + work["course"].map(lambda c: normalize_course(c) or "")
        + "|"
        + work[name_col].map(lambda h: normalize_horse_name(h))
    )


def coverage_report(db: Path, *, start: str | None = None, end: str | None = None) -> dict[str, Any]:
    init_db(db)
    where = "finish_pos IS NOT NULL"
    params: list[Any] = []
    if start:
        where += " AND race_date >= ?"
        params.append(start)
    if end:
        where += " AND race_date <= ?"
        params.append(end)
    with connect(db) as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM runners WHERE {where}", params).fetchone()[0]
        per_col: dict[str, float] = {}
        for col in _BACKFILL_COLUMNS:
            try:
                filled = conn.execute(
                    f"SELECT COUNT(*) FROM runners WHERE {where} AND {col} IS NOT NULL",
                    params,
                ).fetchone()[0]
            except Exception:
                filled = 0
            per_col[col] = round(100.0 * filled / total, 2) if total else 0.0
        enriched = conn.execute(
            f"SELECT COUNT(*) FROM runners WHERE {where} AND enrich_source IS NOT NULL",
            params,
        ).fetchone()[0]
    out = {
        "finished_runners": int(total),
        "enriched_rows": int(enriched),
        "enriched_pct": round(100.0 * enriched / total, 2) if total else 0.0,
        "column_coverage_pct": per_col,
        "mean_enrich_coverage_pct": round(sum(per_col.values()) / len(per_col), 2) if per_col else 0.0,
    }
    if start or end:
        out["window"] = {"start": start, "end": end}
    return out


def _load_racecard_enrich_frames(racecards_dir: Path, *, card_date: str | None = None) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    paths = sorted(racecards_dir.glob("*.json"))
    if card_date:
        target = racecards_dir / f"{card_date}.json"
        paths = [target] if target.exists() else []
    for path in paths:
        try:
            frame = parse_racecard_json(path)
        except (OSError, ValueError):
            continue
        if frame.empty:
            continue
        frame["race_date"] = frame["card_date"]
        frames.append(frame)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    return compute_enrich_ranker_fields(out)


def _sql_val(val: Any) -> Any | None:
    if val is None:
        return None
    if isinstance(val, float) and pd.isna(val):
        return None
    if val is pd.NA:
        return None
    try:
        if pd.isna(val):
            return None
    except (TypeError, ValueError):
        pass
    return val


def _apply_enrich_updates(
    db: Path,
    enrich: pd.DataFrame,
    *,
    source: str,
    card_date: str | None = None,
) -> int:
    if enrich.empty:
        return 0
    init_db(db)
    enrich = compute_enrich_ranker_fields(enrich)
    enrich["_ej"] = _historical_join_key(enrich)
    enrich["_ej_loose"] = _historical_join_key_loose(enrich)
    enrich = enrich.drop_duplicates(subset=["_ej_loose"], keep="last")
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    updated = 0
    strict_matches = 0
    loose_matches = 0
    with connect(db) as conn:
        date_clause = ""
        params: list[Any] = []
        if card_date:
            date_clause = " AND race_date = ?"
            params.append(card_date)
        runners = pd.read_sql_query(
            f"""
            SELECT runner_id, race_date, course, off_time, horse_id, distance_f
            FROM runners
            WHERE finish_pos IS NOT NULL{date_clause}
            """,
            conn,
            params=params or None,
        )
        if runners.empty:
            return 0
        runners["horse_name"] = runners["horse_id"]
        runners["card_date"] = runners["race_date"]
        runners["_ej"] = _historical_join_key(runners)
        runners["_ej_loose"] = _historical_join_key_loose(runners)

        enrich_strict = enrich.set_index("_ej", drop=False)
        enrich_loose = enrich.set_index("_ej_loose", drop=False)

        for _, row in runners.iterrows():
            ej = row["_ej"]
            ej_loose = row["_ej_loose"]
            join_mode = None
            if ej in enrich_strict.index:
                src_row = enrich_strict.loc[ej]
                if isinstance(src_row, pd.DataFrame):
                    src_row = src_row.iloc[-1]
                join_mode = "strict"
            elif ej_loose in enrich_loose.index:
                src_row = enrich_loose.loc[ej_loose]
                if isinstance(src_row, pd.DataFrame):
                    src_row = src_row.iloc[-1]
                join_mode = "loose"
            else:
                continue

            sets: list[str] = []
            vals: list[Any] = []
            for col in _BACKFILL_COLUMNS:
                val = _sql_val(src_row.get(col))
                if val is None:
                    continue
                sets.append(f"{col} = ?")
                vals.append(val)

            off_time = _sql_val(src_row.get("off_time"))
            if off_time and (row.get("off_time") is None or str(row.get("off_time")).strip() == ""):
                sets.append("off_time = ?")
                vals.append(off_time)

            if not sets:
                continue
            sets.extend(["enrich_source = ?", "enriched_at = ?"])
            vals.extend([source, now, row["runner_id"]])
            conn.execute(
                f"UPDATE runners SET {', '.join(sets)} WHERE runner_id = ?",
                vals,
            )
            updated += 1
            if join_mode == "strict":
                strict_matches += 1
            elif join_mode == "loose":
                loose_matches += 1
        conn.commit()
    return {
        "rows_updated": updated,
        "strict_join_matches": strict_matches,
        "loose_join_matches": loose_matches,
    }


def backfill_runner_enrich(
    database: Path | None = None,
    *,
    racecards_dir: Path | None = None,
    include_upcoming: bool = True,
    card_date: str | None = None,
) -> dict[str, Any]:
    """
    Populate runners enrich columns from upcoming_runners and cached RP racecard JSON.
    Does not invent RP stats — only writes values from known sources.
    """
    cfg = load_config()
    db = database or db_path(cfg)
    init_db(db)
    before = coverage_report(db)

    stats: dict[str, Any] = {
        "before": before,
        "from_upcoming": 0,
        "from_racecards": 0,
    }

    if include_upcoming:
        with connect(db) as conn:
            try:
                up = pd.read_sql_query(
                    f"""
                    SELECT u.*, r.runner_id AS hist_runner_id
                    FROM upcoming_runners u
                    INNER JOIN runners r ON r.runner_id = u.runner_id
                    WHERE r.finish_pos IS NOT NULL
                    """,
                    conn,
                )
            except (OSError, ValueError):
                up = pd.DataFrame()
        if not up.empty:
            up["race_date"] = up["card_date"]
            stats["from_upcoming"] = _apply_enrich_updates(
                db, up, source="upcoming_runners", card_date=card_date
            )

    cards_dir = racecards_dir or RPSCRAPE_RACECARDS
    if cards_dir.exists():
        card_frame = _load_racecard_enrich_frames(cards_dir, card_date=card_date)
        stats["from_racecards"] = _apply_enrich_updates(
            db, card_frame, source="rpscrape_racecards", card_date=card_date
        )

    after = coverage_report(db)
    stats["after"] = after
    join_totals = {"strict_join_matches": 0, "loose_join_matches": 0}
    for key in ("from_upcoming", "from_racecards"):
        block = stats.get(key)
        if isinstance(block, dict):
            join_totals["strict_join_matches"] += int(block.get("strict_join_matches", 0))
            join_totals["loose_join_matches"] += int(block.get("loose_join_matches", 0))
        elif isinstance(block, int):
            join_totals["loose_join_matches"] += block
    stats.update(join_totals)
    stats["rows_updated"] = join_totals["strict_join_matches"] + join_totals["loose_join_matches"]
    stats["message"] = (
        f"Backfill complete: {stats['rows_updated']} runner rows updated "
        f"(strict={join_totals['strict_join_matches']}, loose={join_totals['loose_join_matches']}); "
        f"mean enrich coverage {after['mean_enrich_coverage_pct']:.1f}% "
        f"(was {before['mean_enrich_coverage_pct']:.1f}%)."
    )
    return stats
