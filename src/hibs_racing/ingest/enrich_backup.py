"""Backup enrich sources when RP scrape/API is unavailable."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd

from hibs_racing.config import db_path, load_config
from hibs_racing.entity.natural_key import normalize_course
from hibs_racing.features.store import connect, init_db
from hibs_racing.features.runner_enrich_backfill import coverage_report

_PLACE_CUTOFF = 3
_DERIVED_COLUMNS: tuple[str, ...] = (
    "horse_course_win_rate",
    "horse_distance_win_rate",
    "horse_going_win_rate",
    "jockey_rp_14d_win_rate",
    "trainer_rp_14d_win_rate",
    "trainer_14d_strike",
    "form_lto_position",
    "form_poor_runs_3",
)


def _load_history(db, *, until_date: str) -> pd.DataFrame:
    init_db(db)
    with connect(db) as conn:
        frame = pd.read_sql_query(
            """
            SELECT runner_id, race_id, race_date, horse_id, course, going, distance_f,
                   jockey, trainer, finish_pos, enrich_source
            FROM runners
            WHERE finish_pos IS NOT NULL AND race_date <= ?
            ORDER BY race_date, race_id, runner_id
            """,
            conn,
            params=(until_date,),
        )
    if frame.empty:
        return frame
    frame["race_date"] = pd.to_datetime(frame["race_date"])
    frame["won"] = frame["finish_pos"].eq(1).astype(int)
    frame["placed"] = (frame["finish_pos"] <= _PLACE_CUTOFF).astype(int)
    frame["course_key"] = frame["course"].map(lambda c: normalize_course(c) or str(c))
    return frame


def _rolling_entity_rate(frame: pd.DataFrame, entity_col: str, *, window_days: int = 14) -> pd.Series:
    """Point-in-time win rate in prior `window_days` (exclusive of current row date)."""
    out = pd.Series(index=frame.index, dtype=float)
    for entity, grp in frame.groupby(entity_col, sort=False):
        grp = grp.sort_values("race_date")
        dates = grp["race_date"]
        wins = grp["won"]
        for idx in grp.index:
            d = dates.loc[idx]
            start = d - timedelta(days=window_days)
            mask = (dates < d) & (dates >= start)
            runs = int(mask.sum())
            out.loc[idx] = float(wins[mask].sum() / runs) if runs > 0 else None
    return out


def _expanding_horse_rate(frame: pd.DataFrame, segment_col: str) -> pd.Series:
    """Prior-run win rate for horse within segment (course / going / distance bucket)."""
    out = pd.Series(index=frame.index, dtype=float)
    key_cols = ["horse_id", segment_col]
    for _, grp in frame.groupby(key_cols, sort=False):
        grp = grp.sort_values("race_date")
        prior_runs = grp["won"].expanding().count().shift(1)
        prior_wins = grp["won"].expanding().sum().shift(1)
        rate = prior_wins / prior_runs
        out.loc[grp.index] = rate
    return out


def _form_derived(frame: pd.DataFrame) -> pd.DataFrame:
    """Derive simple form signals from prior finishes (no RP form string)."""
    out = frame.copy()
    out["form_lto_position"] = pd.NA
    out["form_poor_runs_3"] = 0
    for horse_id, grp in out.groupby("horse_id", sort=False):
        grp = grp.sort_values("race_date")
        lto = grp["finish_pos"].shift(1)
        out.loc[grp.index, "form_lto_position"] = lto
        poor = grp["finish_pos"].shift(1).rolling(3, min_periods=1).apply(
            lambda s: int((s > _PLACE_CUTOFF).sum()), raw=False
        )
        out.loc[grp.index, "form_poor_runs_3"] = poor.fillna(0).astype(int)
    return out


def derive_enrich_for_date(
    card_date: str,
    *,
    database=None,
    only_missing: bool = True,
) -> dict[str, Any]:
    """
    Point-in-time enrich derived from ingested raceform history (offline backup).
    Does not invent trainer_rtf — that remains RP-only.
    """
    db = database or db_path(load_config())
    before = coverage_report(db)
    hist = _load_history(db, until_date=card_date)
    if hist.empty:
        return {
            "card_date": card_date,
            "rows_updated": 0,
            "before": before,
            "after": before,
            "message": f"No historical runners on or before {card_date}.",
        }

    hist = _form_derived(hist)
    hist["horse_course_win_rate"] = _expanding_horse_rate(hist, "course_key")
    hist["horse_going_win_rate"] = _expanding_horse_rate(hist, "going")
    if hist["distance_f"].notna().any():
        hist["_dist_bucket"] = pd.to_numeric(hist["distance_f"], errors="coerce").round(1)
        hist["horse_distance_win_rate"] = _expanding_horse_rate(hist, "_dist_bucket")
    else:
        hist["horse_distance_win_rate"] = None

    hist["jockey_rp_14d_win_rate"] = _rolling_entity_rate(hist, "jockey")
    hist["trainer_rp_14d_win_rate"] = _rolling_entity_rate(hist, "trainer")
    hist["trainer_14d_strike"] = hist["trainer_rp_14d_win_rate"]

    target = hist[hist["race_date"].eq(pd.Timestamp(card_date))].copy()
    if target.empty:
        return {
            "card_date": card_date,
            "rows_updated": 0,
            "before": before,
            "after": before,
            "message": f"No finished runners on {card_date}.",
        }

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    updated = 0
    init_db(db)
    with connect(db) as conn:
        for rec in target.to_dict(orient="records"):
            if only_missing:
                row = conn.execute(
                    "SELECT enrich_source FROM runners WHERE runner_id = ?",
                    (rec["runner_id"],),
                ).fetchone()
                if row and row[0]:
                    continue
            sets: list[str] = []
            vals: list[Any] = []
            for col in _DERIVED_COLUMNS:
                val = rec.get(col)
                if val is None or (isinstance(val, float) and pd.isna(val)):
                    continue
                sets.append(f"{col} = ?")
                vals.append(val)
            if not sets:
                continue
            sets.extend(["enrich_source = ?", "enriched_at = ?"])
            vals.extend(["raceform_derived", now, rec["runner_id"]])
            conn.execute(
                f"UPDATE runners SET {', '.join(sets)} WHERE runner_id = ?",
                vals,
            )
            updated += 1
        conn.commit()

    after = coverage_report(db)
    return {
        "card_date": card_date,
        "rows_updated": updated,
        "before": before,
        "after": after,
        "message": (
            f"Derived enrich for {card_date}: {updated} rows updated; "
            f"coverage {before['mean_enrich_coverage_pct']:.2f}% → {after['mean_enrich_coverage_pct']:.2f}%."
        ),
    }


def fetch_racecards_with_fallback(
    card_date: str,
    *,
    skip_cached: bool = True,
    use_derived_on_failure: bool = True,
    database=None,
) -> dict[str, Any]:
    """
    Cascade: cached JSON → RP API → raceform-derived DB fill (no external fetch).
    """
    from hibs_racing.ingest.historical_racecards import fetch_historical_racecards_on_date
    from hibs_racing.ingest.racecards import RPSCRAPE_RACECARDS
    from hibs_racing.features.runner_enrich_backfill import backfill_runner_enrich

    result: dict[str, Any] = {"card_date": card_date, "stages": []}
    json_path = RPSCRAPE_RACECARDS / f"{card_date}.json"
    db = database or db_path(load_config())

    if skip_cached and json_path.exists():
        result["stages"].append({"stage": "cached_json", "ok": True})
    else:
        try:
            fetch_historical_racecards_on_date(card_date)
            result["stages"].append({"stage": "rp_api", "ok": True})
        except Exception as exc:
            result["stages"].append({"stage": "rp_api", "ok": False, "error": str(exc)})
            if use_derived_on_failure:
                derived = derive_enrich_for_date(card_date, database=db)
                result["stages"].append({"stage": "raceform_derived", "ok": True, **derived})
                result["rows_backfilled"] = derived.get("rows_updated", 0)
                result["source"] = "raceform_derived"
                return result
            raise

    if not json_path.exists():
        return result

    bf = backfill_runner_enrich(database=db, include_upcoming=False, card_date=card_date)
    result["rows_backfilled"] = int(bf.get("rows_updated", 0))
    result["source"] = "rpscrape_racecards"
    result["stages"].append(
        {
            "stage": "backfill",
            "ok": True,
            "rows": result["rows_backfilled"],
            "strict_join_matches": int(bf.get("strict_join_matches", 0)),
            "loose_join_matches": int(bf.get("loose_join_matches", 0)),
        }
    )
    return result
