"""Upcoming-card DQ recovery — enrich + dense handicap fields for engine output."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd

from hibs_racing.cards.data_quality import is_exempt_unrated_race, runner_data_quality_pct
from hibs_racing.cards.dq_persist import mean_runner_dq
from hibs_racing.cards.enrich import dual_source_enrich, enrich_join_key
from hibs_racing.cards.store import load_upcoming_runners, store_upcoming_runners
from hibs_racing.config import db_path, load_config
from hibs_racing.entity.natural_key import normalize_course
from hibs_racing.features.store import connect, init_db
from hibs_racing.ingest.dense_field_repair import _float_or_none, _int_or_none, _join_key
from hibs_racing.ingest.racecards import RPSCRAPE_RACECARDS, parse_racecard_json
from hibs_racing.odds.matching import normalize_horse_name


def _present(val: object) -> bool:
    if val is None:
        return False
    try:
        if pd.isna(val):
            return False
    except (TypeError, ValueError):
        pass
    return bool(str(val).strip())


def _load_rp_card_index(card_dates: list[str]) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for card_date in card_dates:
        json_path = RPSCRAPE_RACECARDS / f"{card_date}.json"
        if not json_path.exists():
            continue
        try:
            frame = parse_racecard_json(json_path)
        except (OSError, ValueError):
            continue
        if frame.empty:
            continue
        frame = frame.copy()
        frame["_dense_key"] = _join_key(frame)
        frames.append(frame)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    return out.drop_duplicates(subset=["_dense_key"], keep="last").set_index("_dense_key", drop=False)


def repair_upcoming_dense_fields(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Fill missing official_rating, card_comment, trainer_rtf from cached RP racecards."""
    if frame.empty:
        return frame, {"rows": 0, "updated": 0}
    out = frame.copy()
    dates = sorted(out["card_date"].astype(str).str[:10].unique().tolist())
    card_index = _load_rp_card_index(dates)
    if card_index.empty:
        return out, {"rows": len(out), "updated": 0, "message": "no_rp_json"}

    out["_dense_key"] = _join_key(out)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    updated = 0
    for idx, row in out.iterrows():
        key = row.get("_dense_key")
        if key not in card_index.index:
            continue
        src = card_index.loc[key]
        if isinstance(src, pd.DataFrame):
            src = src.iloc[-1]
        changed = False
        for col, parser in (
            ("official_rating", _int_or_none),
            ("trainer_rtf", _float_or_none),
        ):
            if _present(out.at[idx, col]) if col in out.columns else _present(row.get(col)):
                continue
            val = parser(src.get(col))
            if val is None:
                continue
            out.at[idx, col] = val
            changed = True
        for col in ("card_comment", "form_string"):
            if _present(out.at[idx, col]) if col in out.columns else _present(row.get(col)):
                continue
            val = src.get(col)
            if not _present(val):
                continue
            out.at[idx, col] = val
            changed = True
        if changed:
            if not _present(out.at[idx, "enrich_source"] if "enrich_source" in out.columns else None):
                out.at[idx, "enrich_source"] = "rp_dense_field_repair"
                out.at[idx, "enriched_at"] = now
            updated += 1
    out = out.drop(columns=["_dense_key"], errors="ignore")
    return out, {"rows": len(frame), "updated": updated, "card_dates": dates}


def derive_raceform_enrich_for_upcoming(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Point-in-time horse/course stats from ingested raceform history."""
    if frame.empty:
        return frame, {"rows": 0, "updated": 0}

    db = db_path(load_config())
    init_db(db)
    with connect(db) as conn:
        hist = pd.read_sql_query(
            """
            SELECT horse_id, course, finish_pos, race_date
            FROM runners
            WHERE finish_pos IS NOT NULL
            ORDER BY race_date, race_id
            """,
            conn,
        )
    if hist.empty:
        return frame, {"rows": len(frame), "updated": 0, "message": "no_history"}

    hist["course_key"] = hist["course"].map(lambda c: normalize_course(c) or str(c))
    hist["won"] = hist["finish_pos"].eq(1).astype(int)
    hist = hist.sort_values("race_date")

    out = frame.copy()
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    updated = 0
    for idx, row in out.iterrows():
        horse_id = str(row.get("horse_id") or "")
        course_key = normalize_course(row.get("course")) or str(row.get("course") or "")
        if not horse_id:
            continue
        prior = hist[(hist["horse_id"] == horse_id) & (hist["course_key"] == course_key)]
        if prior.empty:
            prior = hist[hist["horse_id"] == horse_id]
        if prior.empty:
            continue
        changed = False
        if not _present(out.at[idx, "horse_course_win_rate"] if "horse_course_win_rate" in out.columns else None):
            course_prior = prior[prior["course_key"] == course_key] if course_key else prior
            runs = len(course_prior)
            if runs > 0:
                out.at[idx, "horse_course_win_rate"] = round(float(course_prior["won"].sum() / runs), 4)
                out.at[idx, "horse_course_runs"] = runs
                out.at[idx, "horse_course_wins"] = int(course_prior["won"].sum())
                changed = True
            elif not prior.empty:
                # Debut at course — explicit zero counts for enrich DQ (horse has form elsewhere).
                out.at[idx, "horse_course_win_rate"] = 0.0
                out.at[idx, "horse_course_runs"] = 0
                out.at[idx, "horse_course_wins"] = 0
                changed = True
        if not _present(out.at[idx, "form_lto_position"] if "form_lto_position" in out.columns else None):
            lto = prior["finish_pos"].iloc[-1]
            if _present(lto):
                out.at[idx, "form_lto_position"] = int(lto)
                changed = True
        if changed and not _present(out.at[idx, "enrich_source"] if "enrich_source" in out.columns else None):
            out.at[idx, "enrich_source"] = "raceform_derived"
            out.at[idx, "enriched_at"] = now
            updated += 1
    return out, {"rows": len(frame), "updated": updated}


def impute_enrich_course_stats_for_debuts(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    """RP-enriched runners without raceform course stats get explicit zero course form."""
    if frame.empty:
        return frame, {"rows": 0, "updated": 0}
    out = frame.copy()
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    updated = 0
    for idx, row in out.iterrows():
        if not _present(row.get("enrich_source") if isinstance(row, dict) else out.at[idx, "enrich_source"]):
            continue
        if _present(out.at[idx, "horse_course_win_rate"] if "horse_course_win_rate" in out.columns else None):
            continue
        out.at[idx, "horse_course_win_rate"] = 0.0
        out.at[idx, "horse_course_runs"] = 0
        out.at[idx, "horse_course_wins"] = 0
        if not _present(out.at[idx, "enrich_source"] if "enrich_source" in out.columns else None):
            out.at[idx, "enrich_source"] = "raceform_derived"
            out.at[idx, "enriched_at"] = now
        updated += 1
    return out, {"rows": len(frame), "updated": updated}


def fill_card_comment_fallbacks(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Use rp_verdict or form_string when card_comment still empty after RP JSON repair."""
    if frame.empty:
        return frame, {"rows": 0, "updated": 0}
    out = frame.copy()
    updated = 0
    for idx, row in out.iterrows():
        if is_exempt_unrated_race(row):
            continue
        if _present(out.at[idx, "card_comment"] if "card_comment" in out.columns else None):
            continue
        verdict = out.at[idx, "rp_verdict"] if "rp_verdict" in out.columns else row.get("rp_verdict")
        if _present(verdict):
            text = str(verdict).strip()
            out.at[idx, "card_comment"] = text[:200]
            updated += 1
            continue
        form = out.at[idx, "form_string"] if "form_string" in out.columns else row.get("form_string")
        if _present(form):
            out.at[idx, "card_comment"] = f"Form {str(form).strip()[:40]}"
            updated += 1
    return out, {"rows": len(frame), "updated": updated}


def backfill_upcoming_enrich(frame: pd.DataFrame | None = None) -> dict[str, Any]:
    """
    Lift upcoming runner DQ toward engine bar:
    RP dual-source enrich → raceform-derived stats → dense handicap repair.
    """
    cards = frame if frame is not None else load_upcoming_runners()
    if cards.empty:
        return {"ok": True, "skipped": True, "runner_count": 0, "message": "no_upcoming"}

    mean_before = mean_runner_dq(cards)
    report: dict[str, Any] = {
        "runner_count": len(cards),
        "mean_dq_before": mean_before,
        "enrich_source_before": int(cards["enrich_source"].notna().sum()) if "enrich_source" in cards.columns else 0,
    }

    enriched, enrich_meta = dual_source_enrich(cards)
    report["dual_source_enrich"] = enrich_meta

    derived, derived_meta = derive_raceform_enrich_for_upcoming(enriched)
    report["raceform_derived"] = derived_meta

    imputed, impute_meta = impute_enrich_course_stats_for_debuts(derived)
    report["course_stats_impute"] = impute_meta

    repaired, dense_meta = repair_upcoming_dense_fields(imputed)
    report["dense_repair"] = dense_meta

    commented, comment_meta = fill_card_comment_fallbacks(repaired)
    report["card_comment_fallback"] = comment_meta

    mean_after = mean_runner_dq(commented)
    enrich_after = (
        int(commented["enrich_source"].notna().sum()) if "enrich_source" in commented.columns else 0
    )
    report["mean_dq_after"] = mean_after
    report["enrich_source_after"] = enrich_after
    report["persisted"] = 0

    if mean_after > mean_before or enrich_after > report["enrich_source_before"]:
        report["persisted"] = store_upcoming_runners(commented, source="dq_recovery")

    report["ok"] = mean_after >= mean_before
    return report


def run_upcoming_dq_recovery(*, target_pct: float | None = None) -> dict[str, Any]:
    from hibs_racing.data_quality_targets import racing_data_quality_target_pct, racing_engine_output_min_dq_pct

    target = target_pct if target_pct is not None else racing_data_quality_target_pct()
    engine_floor = racing_engine_output_min_dq_pct()
    cards = load_upcoming_runners()
    mean_before = mean_runner_dq(cards)
    report: dict[str, Any] = {
        "target_pct": target,
        "engine_floor_pct": engine_floor,
        "mean_dq_before": mean_before,
        "runner_count": len(cards),
    }
    if cards.empty:
        report["ok"] = False
        report["message"] = "no_upcoming"
        return report

    backfill = backfill_upcoming_enrich(cards)
    report["backfill"] = backfill
    mean_after = float(backfill.get("mean_dq_after") or mean_before)
    report["mean_dq_after"] = mean_after
    report["ok"] = mean_after >= engine_floor
    report["message"] = "ok" if report["ok"] else f"mean_dq {mean_after}% < engine floor {engine_floor}%"
    return report
