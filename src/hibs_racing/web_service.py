from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from hibs_racing.cards.query import load_scored_cards
from hibs_racing.cards.window import filter_next_hours, off_minutes
from hibs_racing.backtest.place_signal import run_place_backtest
from hibs_racing.cards.refresh import refresh_cards
from hibs_racing.cards.store import load_upcoming_runners
from hibs_racing.config import db_path, load_config
from hibs_racing.entity.natural_key import generate_natural_key
from hibs_racing.features.store import connect, init_db
from hibs_racing.pick_explain import attach_pick_explanations, explain_pick
from hibs_racing.race_insights import build_race_insights


@dataclass
class HealthStatus:
    db_ok: bool
    runners_loaded: int
    scores_loaded: int
    racing_api: bool
    racing_post: bool
    matchbook: bool
    raceform_path: str | None

    def to_dict(self) -> dict:
        return {
            "db_ok": self.db_ok,
            "runners_loaded": self.runners_loaded,
            "scores_loaded": self.scores_loaded,
            "racing_api": self.racing_api,
            "racing_post": self.racing_post,
            "matchbook": self.matchbook,
            "raceform_path": self.raceform_path,
        }


def _env_ok(*keys: str) -> bool:
    for key in keys:
        if not os.environ.get(key, "").strip():
            return False
    return True


def health_status() -> HealthStatus:
    db = db_path(load_config())
    init_db(db)
    runners = load_upcoming_runners(db)
    scores = 0
    with connect(db) as conn:
        row = conn.execute("SELECT COUNT(*) FROM card_scores").fetchone()
        scores = int(row[0]) if row else 0
    raceform = os.environ.get("RACEFORM_DB_PATH", "").strip() or None
    if raceform:
        raceform = str(Path(raceform).expanduser())
        if not Path(raceform).exists():
            raceform = None
    return HealthStatus(
        db_ok=db.exists(),
        runners_loaded=len(runners),
        scores_loaded=scores,
        racing_api=_env_ok("RACING_API_USERNAME", "RACING_API_PASSWORD"),
        racing_post=_env_ok("EMAIL", "ACCESS_TOKEN"),
        matchbook=_env_ok("MATCHBOOK_USERNAME", "MATCHBOOK_PASSWORD"),
        raceform_path=raceform,
    )


def _offered_place_decimal(row: dict | pd.Series, *, default_fraction: float = 0.25) -> float | None:
    win = row.get("offered_place_decimal") or row.get("win_decimal")
    if win is None or (isinstance(win, float) and pd.isna(win)):
        return None
    try:
        win_f = float(win)
    except (TypeError, ValueError):
        return None
    if win_f <= 1:
        return None
    frac = row.get("place_fraction")
    try:
        pf = float(frac) if frac is not None and not (isinstance(frac, float) and pd.isna(frac)) else default_fraction
    except (TypeError, ValueError):
        pf = default_fraction
    return round(1.0 + (win_f - 1.0) * pf, 2)


def _enrich_runner(row: dict, peers: pd.DataFrame) -> dict:
    explained = explain_pick(row, race_peers=peers)
    row["engine_opinion"] = explained.get("pick_summary")
    row["engine_reasons"] = explained.get("pick_reasons") or []
    place = _offered_place_decimal(row)
    if place is not None:
        row["offered_place_decimal"] = place
    comment = (row.get("card_comment") or "").strip()
    row["rp_comment_short"] = (comment[:120] + "…") if len(comment) > 120 else comment
    return row


def group_meetings(frame: pd.DataFrame) -> list[dict]:
    if frame.empty:
        return []
    meetings: list[dict] = []
    group_cols = ["card_date", "course"]
    if "region" in frame.columns and frame["region"].notna().any():
        group_cols = ["card_date", "course", "region"]

    for keys, course_df in frame.groupby(group_cols, sort=False):
        if len(group_cols) == 3:
            card_date, course, region = keys
        else:
            card_date, course = keys
            region = course_df["region"].iloc[0] if "region" in course_df.columns else ""

        races: list[dict] = []
        for race_id, race_df in course_df.groupby("race_id", sort=False):
            race_df = race_df.sort_values("model_place_prob", ascending=False, na_position="last")
            peers = race_df.copy()
            runners = [_enrich_runner(rec, peers) for rec in race_df.to_dict(orient="records")]
            first = race_df.iloc[0]
            insights = build_race_insights(race_df)
            value_n = int((race_df.get("value_flag", 0) == 1).sum()) if "value_flag" in race_df.columns else 0
            races.append(
                {
                    "race_id": race_id,
                    "race_slug": f"r{len(races) + 1}",
                    "off_time": first.get("off_time"),
                    "off_minutes": off_minutes(first.get("off_time")),
                    "race_name": first.get("race_name"),
                    "race_class": first.get("race_class"),
                    "going": first.get("going"),
                    "distance_f": first.get("distance_f"),
                    "field_size": first.get("field_size") or len(race_df),
                    "card_date": str(card_date),
                    "race_natural_key": first.get("race_natural_key")
                    or generate_natural_key(
                        str(first.get("card_date") or ""),
                        first.get("course"),
                        first.get("off_time"),
                    ),
                    "value_count": value_n,
                    "insights": insights,
                    "runners": runners,
                }
            )
        races.sort(key=lambda r: (r.get("off_minutes") or 9999, str(r.get("race_name") or "")))
        off_times = [str(r.get("off_time") or "") for r in races if r.get("off_time")]
        meetings.append(
            {
                "course": course,
                "card_date": str(card_date),
                "region": str(region or "").upper(),
                "slug": "",
                "races": races,
                "race_count": len(races),
                "runner_count": len(course_df),
                "value_count": int((course_df.get("value_flag", 0) == 1).sum()) if "value_flag" in course_df.columns else 0,
                "first_off_minutes": races[0]["off_minutes"] if races else 9999,
            }
        )

    meetings.sort(key=lambda m: (m.get("card_date", ""), m.get("first_off_minutes") or 9999, str(m.get("course") or "")))
    for idx, meeting in enumerate(meetings):
        base = f"{meeting.get('card_date', '')}-{meeting.get('course') or 'meeting'}".lower()
        slug = "".join(ch if ch.isalnum() or ch == "-" else "-" for ch in base.replace(" ", "-"))
        slug = "-".join(part for part in slug.split("-") if part)[:48] or "meeting"
        meeting["slug"] = f"{idx + 1}-{slug}"
        off_times = [str(r.get("off_time") or "") for r in meeting["races"] if r.get("off_time")]
        meeting["first_off"] = off_times[0] if off_times else "—"
        meeting["last_off"] = off_times[-1] if off_times else "—"
        region_tag = meeting.get("region") or ""
        meeting["label"] = f"{meeting['course']}" + (f" ({region_tag})" if region_tag else "")
    _attach_market_gauges(meetings)
    return meetings


def _attach_market_gauges(meetings: list[dict]) -> None:
    try:
        from hibs_racing.odds.market_steam import evaluate_market_gauges

        gauges = {g.runner_id: g.to_dict() for g in evaluate_market_gauges()}
    except Exception:
        gauges = {}
    for meeting in meetings:
        for race in meeting["races"]:
            for runner in race["runners"]:
                rid = str(runner.get("runner_id") or "")
                runner["market_gauge"] = gauges.get(rid)


def _base_frame(*, card_date: str | None = None, window_hours: int | None = 24) -> pd.DataFrame:
    frame = load_scored_cards()
    if card_date and not frame.empty:
        frame = frame[frame["card_date"].astype(str) == card_date]
    if window_hours and not frame.empty:
        frame = filter_next_hours(frame, hours=window_hours)
    return frame


def insights_context(*, top_n: int = 10, window_hours: int = 24) -> dict:
    from hibs_racing.models.feature_impact import load_feature_impact_report
    from hibs_racing.monitor import top_places_of_day

    frame = _base_frame(window_hours=window_hours)
    picks = top_places_of_day(frame, top_n=top_n)
    feature_impact = load_feature_impact_report()
    scoring_method = None
    if not frame.empty and "scoring_method" in frame.columns:
        modes = frame["scoring_method"].dropna().unique().tolist()
        scoring_method = modes[0] if len(modes) == 1 else "mixed"
    return {
        "top_picks": picks,
        "pick_count": len(picks),
        "runner_count": len(frame),
        "race_count": int(frame["race_id"].nunique()) if not frame.empty else 0,
        "card_dates": sorted(frame["card_date"].astype(str).unique().tolist()) if not frame.empty else [],
        "scoring_method": scoring_method,
        "feature_impact": feature_impact,
        "window_hours": window_hours,
    }


def dashboard_context(*, card_date: str | None = None, window_hours: int = 24) -> dict:
    frame = _base_frame(card_date=card_date, window_hours=window_hours)
    health = health_status()
    value = frame[frame["value_flag"] == 1] if not frame.empty and "value_flag" in frame.columns else frame.iloc[0:0]
    from hibs_racing.monitor import monitor_snapshot, top_places_of_day

    top_picks = top_places_of_day(frame, top_n=10)
    monitor = monitor_snapshot(refresh=False, settle=True)
    backtest = None
    try:
        backtest = run_place_backtest().to_dict()
    except Exception:
        backtest = None
    scoring_method = None
    if not frame.empty and "scoring_method" in frame.columns:
        modes = frame["scoring_method"].dropna().unique().tolist()
        scoring_method = modes[0] if len(modes) == 1 else "mixed"
    from hibs_racing.odds.market_steam import latest_gauges

    card_dates = sorted(frame["card_date"].astype(str).unique().tolist()) if not frame.empty else []
    return {
        "health": health,
        "card_date": card_date or (card_dates[0] if len(card_dates) == 1 else None),
        "card_dates": card_dates,
        "window_hours": window_hours,
        "runner_count": len(frame),
        "race_count": int(frame["race_id"].nunique()) if not frame.empty else 0,
        "value_count": len(value),
        "meetings": group_meetings(frame),
        "top_picks": top_picks,
        "monitor": monitor,
        "backtest": backtest,
        "scoring_method": scoring_method,
        "market_gauges": latest_gauges(limit=100),
        "parquet_path": str(Path(load_config()["paths"]["parquet_dir"]) / "card_scores.parquet"),
    }
