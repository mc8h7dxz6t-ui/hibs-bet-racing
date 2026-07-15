from __future__ import annotations

import os
import time
from datetime import datetime, timezone

import pandas as pd

from hibs_racing.cards.refresh_parallel import parallel_map, timed_ms
from hibs_racing.cards.enrich import dual_source_enrich
from hibs_racing.cards.score_card import score_upcoming_cards
from hibs_racing.cards.store import store_upcoming_runners
from hibs_racing.cards.window import filter_next_hours, primary_card_date
from hibs_racing.config import load_config
from hibs_racing.ingest.rate_limit import (
    racing_api_pause,
    rp_verdict_max_races,
    rp_verdict_race_pause,
    rp_verdict_workers,
)
from hibs_racing.ingest.racecards import load_racecard_frames
from hibs_racing.ingest.racing_api import fetch_racing_api_racecards
from hibs_racing.ingest.rp_verdict import enrich_cards_with_rp_verdicts
from hibs_racing.odds.loader import resolve_scoring_odds


def _cards_cfg() -> dict:
    cfg = dict(load_config().get("cards", {}))
    inc = (os.getenv("HIBS_RACING_INCLUDE_TOMORROW") or "").strip().lower()
    if inc in ("1", "true", "yes", "on"):
        cfg["include_tomorrow"] = True
    elif inc in ("0", "false", "no", "off"):
        cfg["include_tomorrow"] = False
    pdo = (os.getenv("HIBS_RACING_PRIMARY_DATE_ONLY") or "").strip().lower()
    if pdo in ("1", "true", "yes", "on"):
        cfg["primary_date_only"] = True
    elif pdo in ("0", "false", "no", "off"):
        cfg["primary_date_only"] = False
    return cfg


def _parallel_workers() -> int:
    return max(1, int(_cards_cfg().get("parallel_workers", 4)))


def _fetch_cards_window_inner(
    *,
    source: str,
    regions: tuple[str, ...],
    hours: int,
    parallel_workers: int,
) -> pd.DataFrame:
    """Fetch raw cards for GB/IRE without window trim (caller applies filter_next_hours)."""
    cfg = _cards_cfg()
    include_tomorrow = bool(cfg.get("include_tomorrow", False))
    frames: list[pd.DataFrame] = []

    if source == "racing_api":

        def _fetch_region(region: str) -> pd.DataFrame:
            if include_tomorrow:
                return fetch_racing_api_racecards(day=1, days=2, region=region)
            return fetch_racing_api_racecards(day=1, region=region)

        region_pause = racing_api_pause()
        for i, region in enumerate(regions):
            if i > 0 and region_pause > 0:
                time.sleep(region_pause)
            try:
                frames.append(_fetch_region(region))
            except ValueError as exc:
                if "no runners" in str(exc).lower() and len(regions) > 1:
                    continue
                raise
    else:

        def _fetch_rpscrape(region: str) -> pd.DataFrame:
            return load_racecard_frames(days=2, region=region)

        workers = parallel_workers
        if len(regions) > 1 and workers > 1:
            frames = parallel_map(list(regions), _fetch_rpscrape, max_workers=min(workers, len(regions)))
        else:
            for region in regions:
                try:
                    frames.append(_fetch_rpscrape(region))
                except Exception:
                    if region == regions[0]:
                        raise

    if not frames:
        raise RuntimeError("No racecards returned for GB/IRE window.")
    combined = pd.concat(frames, ignore_index=True)
    return combined.drop_duplicates(subset=["runner_id"], keep="last")


def _trim_card_window(frame: pd.DataFrame, *, hours: int) -> pd.DataFrame:
    cfg = _cards_cfg()
    combined = filter_next_hours(frame, hours=hours)
    if cfg.get("primary_date_only", True) and not combined.empty:
        primary = primary_card_date(combined)
        if primary:
            combined = combined[combined["card_date"].astype(str).str[:10] == primary].copy()
    return combined


def fetch_cards_window(
    *,
    source: str = "racing_api",
    regions: tuple[str, ...] = ("gb", "ire"),
    hours: int = 24,
    parallel_workers: int | None = None,
) -> pd.DataFrame:
    """Next N hours of UK + Ireland racecards (today by default; optional tomorrow)."""
    workers = parallel_workers if parallel_workers is not None else _parallel_workers()
    fetch_source = source
    try:
        raw = _fetch_cards_window_inner(
            source=fetch_source,
            regions=regions,
            hours=hours,
            parallel_workers=workers,
        )
    except Exception as exc:
        if fetch_source != "racing_api":
            raise
        from hibs_racing.racing_api_guard import record_forbidden

        record_forbidden(http_status=403, reason=str(exc)[:80])
        raw = _fetch_cards_window_inner(
            source="rpscrape",
            regions=regions,
            hours=hours,
            parallel_workers=workers,
        )
    combined = _trim_card_window(raw, hours=hours)
    if combined.empty and hours < 48:
        widened = _trim_card_window(raw, hours=48)
        if not widened.empty:
            combined = widened
    if combined.empty:
        raise RuntimeError("No racecards in GB/IRE window — check API credentials or off times.")
    return combined


def refresh_cards(
    *,
    source: str = "racing_api",
    region: str = "gb",
    day: int = 1,
    odds_source: str = "auto",
    window_hours: int | None = 24,
    regions: tuple[str, ...] | None = None,
    paper: bool = False,
    parallel_workers: int | None = None,
    poll_milestone: str | None = None,
) -> dict:
    from hibs_racing.scrapers.racing_scrape_api import resolve_cards_source

    source = resolve_cards_source(source)
    workers = parallel_workers if parallel_workers is not None else _parallel_workers()
    timings: dict[str, float] = {}

    if window_hours is not None:
        cards, timings["fetch_ms"] = timed_ms(
            lambda: fetch_cards_window(
                source=source,
                regions=regions or ("gb", "ire"),
                hours=window_hours,
                parallel_workers=workers,
            )
        )
        src = "racing_api" if source == "racing_api" else "rpscrape"
    elif source == "racing_api":
        cards, timings["fetch_ms"] = timed_ms(lambda: fetch_racing_api_racecards(day=day, region=region))
        src = "racing_api"
    else:
        cards, timings["fetch_ms"] = timed_ms(lambda: load_racecard_frames(day=day, region=region))
        src = "rpscrape"

    if cards.empty:
        raise RuntimeError("No runners in card window — check Racing API credentials or off times.")

    enrich_meta: dict = {}
    if source == "racing_api" and _cards_cfg().get("dual_source_enrich", True):
        cards, enrich_meta = dual_source_enrich(
            cards,
            regions=regions or ("gb", "ire"),
            day=day if window_hours is None else 1,
        )

    rp_workers = rp_verdict_workers()
    verdict_pause = rp_verdict_race_pause()
    cards, timings["verdict_ms"] = timed_ms(
        lambda: enrich_cards_with_rp_verdicts(
            cards,
            max_workers=rp_workers,
            sleep_sec=verdict_pause,
            max_races=rp_verdict_max_races(),
            skip_existing=True,
        )
    )

    _, timings["store_ms"] = timed_ms(lambda: store_upcoming_runners(cards, source=src))

    (odds, odds_meta), timings["odds_ms"] = timed_ms(
        lambda: resolve_scoring_odds(cards, odds_source=odds_source, force_live_odds=True)
    )

    try:
        from hibs_racing.odds.exchange_quotes import load_cached_exchange_odds
        from hibs_racing.odds.loader import _merge_odds_frames, _min_odds_coverage_ratio, _odds_coverage

        card_n = max(len(cards), 1)
        cov = _odds_coverage(odds, card_runners=card_n)
        if cov < _min_odds_coverage_ratio():
            cached = load_cached_exchange_odds(cards)
            if cached is not None and not cached.empty:
                merged = _merge_odds_frames(odds, cached)
                if merged is not None and not merged.empty:
                    odds = merged
                    odds_meta = dict(odds_meta)
                    prior = str(odds_meta.get("source") or "none")
                    odds_meta["source"] = "exchange_cache" if prior in ("none", "") else f"{prior}+exchange_cache"
                    odds_meta["exchange_cache_rows"] = len(cached)
    except Exception:
        pass

    milestone = poll_milestone or os.environ.get("HIBS_POLL_MILESTONE", "baseline")
    polled_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    exchange_audit: dict = {"poll_milestone": milestone}

    if odds is not None and not odds.empty:
        from hibs_racing.odds.exchange_quotes import persist_exchange_quotes, quote_coverage_ratio
        from hibs_racing.odds.market_steam import append_odds_history

        if "card_date" not in odds.columns:
            odds = odds.merge(cards[["runner_id", "card_date", "race_id"]], on="runner_id", how="left")
        append_odds_history(odds, polled_at=polled_at)
        exchange_audit["persist"] = persist_exchange_quotes(
            odds, poll_milestone=milestone, polled_at=polled_at
        )
        exchange_audit["coverage_ratio"] = quote_coverage_ratio(odds, card_runners=len(cards))
        if "exchange_spread_bps" in odds.columns:
            spreads = odds["exchange_spread_bps"].dropna()
            if not spreads.empty:
                exchange_audit["median_spread_bps"] = float(spreads.median())
        report = odds_meta.get("report") or {}
        exchange_audit["runners_priced"] = report.get("runners_priced", len(odds))
        prof_cfg = load_config().get("exchange_profiling", {})
        min_cov = float(prof_cfg.get("min_coverage_ratio", 0.80))
        cov = exchange_audit.get("coverage_ratio")
        if cov is not None and cov < min_cov:
            exchange_audit["coverage_warning"] = (
                f"Matchbook priced {cov:.0%} of card runners (floor {min_cov:.0%})"
            )

    from hibs_racing.cards.engine_profile import build_engine_profile

    engine_profile = build_engine_profile()

    scored, timings["score_ms"] = timed_ms(
        lambda: score_upcoming_cards(
            cards,
            odds=odds if odds is not None and not odds.empty else None,
            write_snapshot=True,
            snapshot_odds_source=str(odds_meta.get("source") or "live"),
        )
    )

    from hibs_racing.cards.lane_paper import attach_lane_flags, sync_lane_paper_ledger

    scored = attach_lane_flags(scored)

    from hibs_racing.institutional.ledger_events import append_ledger_event
    from hibs_racing.institutional.run_manifest import build_run_manifest, persist_run_manifest
    from hibs_racing.institutional.shadow_execution import log_shadow_intents

    card_dates = sorted(cards["card_date"].astype(str).unique().tolist())
    primary_date = card_dates[0] if card_dates else None
    value_n = int((scored["value_flag"] == 1).sum()) if "value_flag" in scored.columns else 0
    manifest = build_run_manifest(
        run_kind="refresh",
        card_date=primary_date,
        scoring_method=str(scored["scoring_method"].iloc[0]) if "scoring_method" in scored.columns and len(scored) else None,
        odds_source=str(odds_meta.get("source")),
        runner_count=len(scored),
        value_flag_count=value_n,
        extras={
            "enrich_matched": enrich_meta.get("matched"),
            "source": src,
            "timings_ms": timings,
            "engine_profile": engine_profile,
            "exchange_audit": exchange_audit,
        },
    )
    manifest_id = persist_run_manifest(manifest)
    append_ledger_event(
        event_type="manifest_written",
        manifest_id=manifest_id,
        payload=manifest.to_dict(),
    )
    shadow_count = 0
    if value_n:
        shadow_count = len(log_shadow_intents(scored, manifest_id=manifest_id, venue="shadow"))

    paper_bets = 0
    recon_clean = True
    recon_by_date: list[dict] = []
    paper_enabled = paper or bool(load_config().get("paper", {}).get("log_on_refresh", True))
    if paper_enabled and "value_flag" in scored.columns and "card_date" in scored.columns:
        from hibs_racing.institutional.paper_reconciliation import sync_paper_ledger_to_scored

        stake = float(load_config().get("paper", {}).get("default_stake", 1.0))
        for card_date in sorted(scored["card_date"].dropna().astype(str).unique()):
            day_scored = scored[scored["card_date"].astype(str) == card_date]
            if day_scored.empty:
                continue
            recon = sync_paper_ledger_to_scored(
                day_scored,
                card_date=str(card_date),
                stake=stake,
                manifest_id=manifest_id,
                odds_source=str(odds_meta.get("source")),
                engine_profile=engine_profile,
            )
            paper_bets += recon.expected_value_picks
            recon_clean = recon_clean and recon.is_clean
            recon_by_date.append(
                {
                    "card_date": str(card_date),
                    "expected": recon.expected_value_picks,
                    "ledger": recon.ledger_value_picks,
                    "clean": recon.is_clean,
                }
            )
            sync_lane_paper_ledger(
                day_scored,
                card_date=str(card_date),
                lane="gate3",
                flag_col="flag_gate3",
                manifest_id=manifest_id,
                odds_source=str(odds_meta.get("source")),
                engine_profile=engine_profile,
            )
        if milestone in ("baseline", "pre_race_30m"):
            from hibs_racing.odds.exchange_quotes import sync_value_picks_from_scored

            sync_value_picks_from_scored(scored, poll_milestone=milestone)

    timings["total_ms"] = round(sum(timings.values()), 1)

    result = {
        "runners": len(cards),
        "races": int(cards["race_id"].nunique()),
        "meetings": int(cards.groupby(["card_date", "course"]).ngroups),
        "card_dates": sorted(cards["card_date"].astype(str).unique().tolist()),
        "regions": sorted(cards.get("region", pd.Series(dtype=str)).dropna().astype(str).str.upper().unique().tolist()),
        "source": src,
        "odds_source": odds_meta.get("source"),
        "odds_runners": exchange_audit.get("runners_priced")
        or (odds_meta.get("report") or {}).get("runners_priced", 0),
        "exchange_audit": exchange_audit,
        "value_flags": int((scored["value_flag"] == 1).sum()) if "value_flag" in scored.columns else 0,
        "value_gates_blocked": int(scored["value_gate_reason"].notna().sum())
        if "value_gate_reason" in scored.columns
        else 0,
        "enrich_matched": enrich_meta.get("matched", 0),
        "enrich_rp_runners": enrich_meta.get("rp_runners", 0),
        "enrich_error": enrich_meta.get("error"),
        "scoring_method": str(scored["scoring_method"].iloc[0]) if "scoring_method" in scored.columns and len(scored) else None,
        "window_hours": window_hours,
        "paper_bets_logged": paper_bets,
        "paper_recon_clean": recon_clean,
        "paper_recon_by_date": recon_by_date,
        "manifest_id": manifest_id,
        "shadow_intents": shadow_count,
        "engine_profile": engine_profile,
        "config_hash": manifest.config_hash,
        "parallel_workers": workers,
        "timings_ms": timings,
    }
    from hibs_racing.institutional.telemetry_balance import record_telemetry_balance
    from hibs_racing.models.ranker_preflight import observation_lane_enabled

    observation_lane = observation_lane_enabled()
    telemetry = record_telemetry_balance(
        result,
        manifest_id=manifest_id,
        observation_lane=observation_lane,
    )
    result["telemetry_balance"] = telemetry.to_dict()
    return result
