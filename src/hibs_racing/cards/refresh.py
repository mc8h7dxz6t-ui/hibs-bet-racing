from __future__ import annotations

import pandas as pd

from hibs_racing.cards.refresh_parallel import parallel_map, timed_ms
from hibs_racing.cards.score_card import paper_log_value_picks, score_upcoming_cards
from hibs_racing.cards.store import store_upcoming_runners
from hibs_racing.cards.window import filter_next_hours
from hibs_racing.config import load_config
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
    """Next N hours of UK + Ireland racecards (today + tomorrow when needed)."""
    workers = parallel_workers if parallel_workers is not None else _parallel_workers()
    frames: list[pd.DataFrame] = []

    if source == "racing_api":

        def _fetch_region(region: str) -> pd.DataFrame:
            return fetch_racing_api_racecards(day=1, days=2, region=region)

        if len(regions) > 1 and workers > 1:
            frames = parallel_map(list(regions), _fetch_region, max_workers=min(workers, len(regions)))
        else:
            for region in regions:
                frames.append(_fetch_region(region))
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
    return filter_next_hours(combined, hours=hours)


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

    rp_workers = int(_cards_cfg().get("rp_verdict_workers", workers))
    cards, timings["verdict_ms"] = timed_ms(
        lambda: enrich_cards_with_rp_verdicts(cards, max_workers=rp_workers)
    )

    _, timings["store_ms"] = timed_ms(lambda: store_upcoming_runners(cards, source=src))

    (odds, odds_meta), timings["odds_ms"] = timed_ms(lambda: resolve_scoring_odds(cards, odds_source=odds_source))

    scored, timings["score_ms"] = timed_ms(
        lambda: score_upcoming_cards(cards, odds=odds if odds is not None and not odds.empty else None)
    )

    paper_bets = 0
    if paper and "value_flag" in scored.columns:
        value = scored[scored["value_flag"] == 1]
        if not value.empty:
            stake = float(load_config().get("paper", {}).get("default_stake", 1.0))
            paper_bets = len(paper_log_value_picks(value, stake=stake))

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
        "scoring_method": str(scored["scoring_method"].iloc[0]) if "scoring_method" in scored.columns and len(scored) else None,
        "window_hours": window_hours,
        "paper_bets_logged": paper_bets,
        "parallel_workers": workers,
        "timings_ms": timings,
    }
