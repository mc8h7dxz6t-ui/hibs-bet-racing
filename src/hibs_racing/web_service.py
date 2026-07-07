from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from hibs_racing.cards.enrich_display import build_enrich_display
from hibs_racing.cards.query import load_scored_cards
from hibs_racing.cards.ui_frame import (
    db_ui_sync_report,
    gate_reason_is_clear,
    is_value_pick,
    safe_value_mask,
)
from hibs_racing.cards.window import filter_next_hours, off_minutes
from hibs_racing.backtest.place_signal import run_place_backtest
from hibs_racing.cards.refresh import refresh_cards
from hibs_racing.cards.store import load_upcoming_runners
from hibs_racing.config import db_path, load_config
from hibs_racing.entity.natural_key import generate_natural_key
from hibs_racing.features.store import connect, init_db
from hibs_racing.pick_explain import attach_pick_explanations, explain_pick
from hibs_racing.ingest.rp_verdict import race_verdict_from_runners
from hibs_racing.live.execution_config import betfair_configured, betfair_enabled
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
    betfair_enabled: bool
    betfair_configured: bool
    analytics_mode: bool
    config_hash: str | None = None
    engine_profile: dict | None = None
    paper_recon_clean: bool | None = None
    manifest_id: str | None = None
    snapshot_coverage_pct: float | None = None
    telemetry_balance: dict | None = None
    db_ui_in_sync: bool | None = None
    unscored_runners: int | None = None
    nan_integrity_passed: bool | None = None
    production_value_count: int | None = None
    place_reliability: dict | None = None
    sale_gates: dict | None = None

    def to_dict(self) -> dict:
        out = {
            "db_ok": self.db_ok,
            "runners_loaded": self.runners_loaded,
            "scores_loaded": self.scores_loaded,
            "racing_api": self.racing_api,
            "racing_post": self.racing_post,
            "matchbook": self.matchbook,
            "raceform_path": self.raceform_path,
            "betfair_enabled": self.betfair_enabled,
            "betfair_configured": self.betfair_configured,
            "analytics_mode": self.analytics_mode,
        }
        if self.config_hash is not None:
            out["config_hash"] = self.config_hash
        if self.engine_profile is not None:
            out["engine_profile"] = self.engine_profile
        if self.paper_recon_clean is not None:
            out["paper_recon_clean"] = self.paper_recon_clean
        if self.manifest_id is not None:
            out["manifest_id"] = self.manifest_id
        if self.snapshot_coverage_pct is not None:
            out["snapshot_coverage_pct"] = self.snapshot_coverage_pct
        if self.telemetry_balance is not None:
            out["telemetry_balance"] = self.telemetry_balance
        if self.db_ui_in_sync is not None:
            out["db_ui_in_sync"] = self.db_ui_in_sync
        if self.unscored_runners is not None:
            out["unscored_runners"] = self.unscored_runners
        if self.nan_integrity_passed is not None:
            out["nan_integrity_passed"] = self.nan_integrity_passed
        if self.production_value_count is not None:
            out["production_value_count"] = self.production_value_count
        if self.place_reliability is not None:
            out["place_reliability"] = self.place_reliability
        if self.sale_gates is not None:
            out["sale_gates"] = self.sale_gates
        return out


def _env_ok(*keys: str) -> bool:
    for key in keys:
        if not os.environ.get(key, "").strip():
            return False
    return True


def health_status() -> HealthStatus:
    from datetime import datetime, timedelta, timezone

    from hibs_racing.backtest.snapshot_store import scoring_config_hash, snapshot_coverage
    from hibs_racing.cards.engine_profile import build_engine_profile
    from hibs_racing.institutional.paper_reconciliation import reconcile_paper_ledger
    from hibs_racing.institutional.run_manifest import latest_manifest_for_date

    cfg = load_config()
    db = db_path(cfg)
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
    today = datetime.now(timezone.utc).date().isoformat()
    end_dt = datetime.now(timezone.utc).date()
    start_dt = (end_dt - timedelta(days=7)).isoformat()
    cov = snapshot_coverage(db, start_dt, end_dt.isoformat())
    manifest = latest_manifest_for_date(today, database=db)
    telemetry_balance = None
    if manifest:
        from hibs_racing.institutional.telemetry_balance import evaluate_telemetry_balance

        observation_lane = os.environ.get("HIBS_OBSERVATION_LANE", "1").strip().lower() in (
            "1",
            "true",
            "yes",
        )
        telemetry_balance = evaluate_telemetry_balance(
            manifest=manifest,
            observation_lane=observation_lane,
        ).to_dict()
    recon_clean = None
    if runners is not None and len(runners) > 0:
        try:
            recon = reconcile_paper_ledger(today, database=db)
            recon_clean = recon.is_clean
        except Exception:
            recon_clean = None
    sync = db_ui_sync_report(database=db)
    from hibs_racing.monitoring.nan_alert import run_nan_integrity_check

    scored = load_scored_cards()
    prod_n = int(safe_value_mask(scored).sum()) if not scored.empty else 0
    nan_report = run_nan_integrity_check(database=db, strict=False)
    place_reliability = None
    try:
        from hibs_racing.analytics.reliability_bins import place_reliability_from_ledger, place_reliability_from_snapshots

        with connect(db) as conn:
            place_reliability = place_reliability_from_ledger(conn, days=60, backtest=False)
            if int(place_reliability.get("n") or 0) < 20:
                snap = place_reliability_from_snapshots(conn, days=60)
                if int(snap.get("n") or 0) > int(place_reliability.get("n") or 0):
                    place_reliability = snap
    except Exception:
        place_reliability = None
    from hibs_racing.sale_gates import sale_gate_status

    return HealthStatus(
        db_ok=db.exists(),
        runners_loaded=len(runners),
        scores_loaded=scores,
        racing_api=_env_ok("RACING_API_USERNAME", "RACING_API_PASSWORD"),
        racing_post=_env_ok("EMAIL", "ACCESS_TOKEN"),
        matchbook=_env_ok("MATCHBOOK_USERNAME", "MATCHBOOK_PASSWORD"),
        raceform_path=raceform,
        betfair_enabled=betfair_enabled(),
        betfair_configured=betfair_configured(),
        analytics_mode=True,
        config_hash=scoring_config_hash(),
        engine_profile=build_engine_profile(cfg),
        paper_recon_clean=recon_clean,
        manifest_id=manifest.manifest_id if manifest else None,
        snapshot_coverage_pct=cov.get("coverage_pct"),
        telemetry_balance=telemetry_balance,
        db_ui_in_sync=bool(sync.get("in_sync")),
        unscored_runners=int(sync.get("unscored_on_card") or 0),
        nan_integrity_passed=nan_report.passed,
        production_value_count=prod_n,
        place_reliability=place_reliability,
        sale_gates=sale_gate_status(),
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
    raw_comment = row.get("card_comment")
    comment = raw_comment.strip() if isinstance(raw_comment, str) else ""
    row["rp_comment_short"] = (comment[:120] + "…") if len(comment) > 120 else comment
    row.update(build_enrich_display(row))
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
            rp_verdict = race_verdict_from_runners(race_df)
            rp_verdict_short = (
                (rp_verdict[:160] + "…") if rp_verdict and len(rp_verdict) > 160 else rp_verdict
            )
            value_n = int(safe_value_mask(race_df).sum()) if "value_flag" in race_df.columns else 0
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
                    "rp_verdict": rp_verdict,
                    "rp_verdict_short": rp_verdict_short,
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
                "value_count": int(safe_value_mask(course_df).sum()) if "value_flag" in course_df.columns else 0,
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


def race_dom_id(meeting_slug: str, race_slug: str) -> str:
    return f"race-{meeting_slug}-{race_slug}"


def resolve_race_deep_link(
    meetings: list[dict],
    *,
    race_id: str | None = None,
    meeting: str | None = None,
    race: str | None = None,
) -> dict[str, str]:
    """
    Map query params → meeting slug + race drawer DOM id for deep-linking.
    Prefer explicit meeting+race; otherwise resolve by race_id.
    """
    meeting = (meeting or "").strip()
    race = (race or "").strip()
    if meeting and race:
        if not race.startswith("race-"):
            race = race_dom_id(meeting, race)
        return {"meeting": meeting, "race": race, "race_id": str(race_id or "")}

    rid = str(race_id or "").strip()
    if not rid:
        return {}

    for m in meetings:
        for r in m.get("races") or []:
            if str(r.get("race_id")) == rid:
                slug = str(m.get("slug") or "")
                dom = race_dom_id(slug, str(r.get("race_slug") or "r1"))
                return {"meeting": slug, "race": dom, "race_id": rid}
    return {}


def attach_deep_links_to_picks(picks: list[dict], meetings: list[dict]) -> list[dict]:
    from hibs_racing.utils.monetization import attach_monetized_links

    out: list[dict] = []
    for pick in picks:
        link = resolve_race_deep_link(meetings, race_id=str(pick.get("race_id") or ""))
        if pick.get("runner_id"):
            link = {**link, "runner_id": str(pick["runner_id"])}
        out.append({**pick, "deep_link": link})
    return attach_monetized_links(out)


def cards_deep_link_context(
    meetings: list[dict],
    *,
    race_id: str | None = None,
    meeting: str | None = None,
    race: str | None = None,
    runner_id: str | None = None,
) -> dict:
    link = resolve_race_deep_link(meetings, race_id=race_id, meeting=meeting, race=race)
    runner = (runner_id or "").strip()
    if runner:
        link = {**link, "runner_id": runner}
    return {
        "deep_link": link,
        "initial_meeting": link.get("meeting"),
        "initial_race": link.get("race"),
        "highlight_runner": runner or link.get("runner_id"),
    }


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
    meetings = group_meetings(frame) if not frame.empty else []
    picks = attach_deep_links_to_picks(top_places_of_day(frame, top_n=top_n), meetings)
    feature_impact = load_feature_impact_report()
    pick_candidates = novice_pick_candidates(meetings)
    scoring_method = None
    if not frame.empty and "scoring_method" in frame.columns:
        modes = frame["scoring_method"].dropna().unique().tolist()
        scoring_method = modes[0] if len(modes) == 1 else "mixed"
    return {
        "top_picks": picks,
        "pick_candidates": pick_candidates,
        "pick_count": len(picks),
        "runner_count": len(frame),
        "race_count": int(frame["race_id"].nunique()) if not frame.empty else 0,
        "card_dates": sorted(frame["card_date"].astype(str).unique().tolist()) if not frame.empty else [],
        "scoring_method": scoring_method,
        "feature_impact": feature_impact,
        "window_hours": window_hours,
    }


def _ui_data_completeness(row: dict) -> int:
    """UI completeness — same logic as Gate1 min_data_quality_pct."""
    from hibs_racing.cards.data_quality import runner_data_quality_pct

    return runner_data_quality_pct(row)


def novice_pick_candidates(meetings: list[dict]) -> list[dict]:
    """Flatten card rows for client-side Smart Portfolio / slip copy (UI layer only)."""
    from hibs_racing.utils.monetization import generate_monetized_link

    out: list[dict] = []
    for meeting in meetings:
        course = meeting.get("course")
        for race in meeting.get("races") or []:
            off_time = race.get("off_time")
            for row in race.get("runners") or []:
                gauge = row.get("market_gauge") or {}
                win = row.get("win_decimal")
                try:
                    win_f = float(win) if win is not None and not (isinstance(win, float) and pd.isna(win)) else None
                except (TypeError, ValueError):
                    win_f = None
                mwp = row.get("model_win_prob")
                try:
                    mwp_f = float(mwp) if mwp is not None and not (isinstance(mwp, float) and pd.isna(mwp)) else None
                except (TypeError, ValueError):
                    mwp_f = None
                implied = mwp_f if mwp_f else ((1.0 / win_f) if win_f and win_f > 1 else None)
                out.append(
                    {
                        "runner_id": row.get("runner_id"),
                        "horse_name": row.get("horse_name"),
                        "course": course,
                        "off_time": off_time,
                        "race_name": race.get("race_name"),
                        "win_decimal": win_f,
                        "implied_prob": implied,
                        "model_place_prob": row.get("model_place_prob"),
                        "place_score": row.get("place_score") or row.get("model_place_prob"),
                        "ew_combined_ev": row.get("ew_combined_ev"),
                        "value_flag": is_value_pick(row.get("value_flag")),
                        "value_gate_reason": None
                        if gate_reason_is_clear(row.get("value_gate_reason"))
                        else row.get("value_gate_reason"),
                        "enrich_source": row.get("enrich_source"),
                        "steam_gate": str(gauge.get("gate") or "proceed"),
                        "kelly_multiplier": float(gauge.get("kelly_multiplier") or 1.0),
                        "data_quality_pct": _ui_data_completeness(row),
                        "stake_units": float(load_config().get("paper", {}).get("default_stake", 1.0)),
                        "bet_type": "each_way",
                        "deep_link": {
                            "meeting": meeting.get("slug"),
                            "race": race_dom_id(str(meeting.get("slug") or ""), str(race.get("race_slug") or "r1")),
                            "runner_id": row.get("runner_id"),
                        },
                        "monetized_link": generate_monetized_link(
                            str(row.get("horse_name") or ""),
                            str(course or ""),
                            str(off_time or ""),
                        ),
                    }
                )
    return out


def dashboard_context(*, card_date: str | None = None, window_hours: int = 24) -> dict:
    frame = _base_frame(card_date=card_date, window_hours=window_hours)
    health = health_status()
    value = frame[safe_value_mask(frame)] if not frame.empty else frame.iloc[0:0]
    from hibs_racing.monitor import monitor_snapshot, top_places_of_day

    monitor = monitor_snapshot(refresh=False, settle=True)
    try:
        backtest = run_place_backtest().to_dict()
    except Exception:
        backtest = None
    scoring_method = None
    if not frame.empty and "scoring_method" in frame.columns:
        modes = frame["scoring_method"].dropna().unique().tolist()
        scoring_method = modes[0] if len(modes) == 1 else "mixed"
    from hibs_racing.odds.market_steam import latest_gauges
    from hibs_racing.ranker_features import ranker_feature_profile
    from hibs_racing.backtest.gate_compare import compare_value_gates

    card_dates = sorted(frame["card_date"].astype(str).unique().tolist()) if not frame.empty else []
    meetings = group_meetings(frame) if not frame.empty else []
    pick_candidates = novice_pick_candidates(meetings)
    try:
        gate_summary = compare_value_gates(days=14).to_dict()
    except Exception:
        gate_summary = None
    return {
        "health": health,
        "card_date": card_date or (card_dates[0] if len(card_dates) == 1 else None),
        "card_dates": card_dates,
        "window_hours": window_hours,
        "runner_count": len(frame),
        "race_count": int(frame["race_id"].nunique()) if not frame.empty else 0,
        "value_count": len(value),
        "meetings": meetings,
        "top_picks": attach_deep_links_to_picks(top_places_of_day(frame, top_n=10), meetings),
        "pick_candidates": pick_candidates,
        "monitor": monitor,
        "backtest": backtest,
        "scoring_method": scoring_method,
        "ranker_profile": ranker_feature_profile(),
        "gate_summary": gate_summary,
        "market_gauges": latest_gauges(limit=100),
        "parquet_path": str(Path(load_config()["paths"]["parquet_dir"]) / "card_scores.parquet"),
    }
