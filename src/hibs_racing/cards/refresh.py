from __future__ import annotations

import os
import time

import pandas as pd

from hibs_racing.cards.refresh_parallel import parallel_map, timed_ms
from hibs_racing.cards.enrich import dual_source_enrich
from hibs_racing.cards.score_card import score_upcoming_cards
from hibs_racing.cards.store import store_upcoming_runners
from hibs_racing.cards.window import filter_next_hours
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
    return load_config().get("cards", {})


def _parallel_workers() -> int:
    return max(1, int(_cards_cfg().get("parallel_workers", 4)))


def fetch_cards_window(
    *,
    source: str = "racing_api",
    regions: tuple[str, ...] = ("gb", "ire"),
    hours: int = 24,
    parallel_workers: int | None = None,
) -> pd.DataFrame:
    """Next N hours of UK + Ireland racecards (today by default; optional tomorrow)."""
    workers = parallel_workers if parallel_workers is not None else _parallel_workers()
    cfg = _cards_cfg()
    include_tomorrow = bool(cfg.get("include_tomorrow", False))
    frames: list[pd.DataFrame] = []

    if source == "racing_api":

        def _fetch_region(region: str) -> pd.DataFrame:
            if include_tomorrow:
                return fetch_racing_api_racecards(day=1, days=2, region=region)
            return fetch_racing_api_racecards(day=1, region=region)

        # Free Racing API tier rate-limits parallel today/tomorrow × region calls.
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
    combined = combined.drop_duplicates(subset=["runner_id"], keep="last")
    combined = filter_next_hours(combined, hours=hours)
    if cfg.get("primary_date_only", True) and not combined.empty:
        dates = pd.to_datetime(combined["card_date"].astype(str), errors="coerce").dropna()
        if not dates.empty:
            primary = dates.min().date().isoformat()
            combined = combined[combined["card_date"].astype(str).str[:10] == primary].copy()
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
) -> dict:
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

    (odds, odds_meta), timings["odds_ms"] = timed_ms(lambda: resolve_scoring_odds(cards, odds_source=odds_source))

    if odds is not None and not odds.empty:
        from hibs_racing.odds.market_steam import append_odds_history

        append_odds_history(odds)

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
    paper_enabled = paper or bool(load_config().get("paper", {}).get("log_on_refresh", True))
    if paper_enabled and "value_flag" in scored.columns and primary_date:
        from hibs_racing.institutional.paper_reconciliation import sync_paper_ledger_to_scored

        stake = float(load_config().get("paper", {}).get("default_stake", 1.0))
        recon = sync_paper_ledger_to_scored(
            scored,
            card_date=str(primary_date),
            stake=stake,
            manifest_id=manifest_id,
            odds_source=str(odds_meta.get("source")),
            engine_profile=engine_profile,
        )
        paper_bets = recon.expected_value_picks
        recon_clean = recon.is_clean

    timings["total_ms"] = round(sum(timings.values()), 1)

    return {
        "runners": len(cards),
        "races": int(cards["race_id"].nunique()),
        "meetings": int(cards.groupby(["card_date", "course"]).ngroups),
        "card_dates": sorted(cards["card_date"].astype(str).unique().tolist()),
        "regions": sorted(cards.get("region", pd.Series(dtype=str)).dropna().astype(str).str.upper().unique().tolist()),
        "source": src,
        "odds_source": odds_meta.get("source"),
        "odds_runners": odds_meta.get("runners_priced", 0),
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
        "manifest_id": manifest_id,
        "shadow_intents": shadow_count,
        "engine_profile": engine_profile,
        "config_hash": manifest.config_hash,
        "parallel_workers": workers,
        "timings_ms": timings,
    }
