from __future__ import annotations

import pandas as pd

from hibs_racing.cards.score_card import paper_log_value_picks, score_upcoming_cards
from hibs_racing.cards.store import store_upcoming_runners
from hibs_racing.cards.window import filter_next_hours
from hibs_racing.config import load_config
from hibs_racing.ingest.racecards import load_racecard_frames
from hibs_racing.ingest.racing_api import fetch_racing_api_racecards
from hibs_racing.odds.loader import resolve_scoring_odds


def fetch_cards_window(
    *,
    source: str = "racing_api",
    regions: tuple[str, ...] = ("gb", "ire"),
    hours: int = 24,
) -> pd.DataFrame:
    """Next N hours of UK + Ireland racecards (today + tomorrow when needed)."""
    frames: list[pd.DataFrame] = []
    if source == "racing_api":
        for region in regions:
            try:
                frames.append(fetch_racing_api_racecards(day=1, days=2, region=region))
            except Exception:
                if region == regions[0]:
                    raise
    else:
        for region in regions:
            try:
                frames.append(load_racecard_frames(days=2, region=region))
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
) -> dict:
    if window_hours is not None:
        cards = fetch_cards_window(source=source, regions=regions or ("gb", "ire"), hours=window_hours)
        src = "racing_api" if source == "racing_api" else "rpscrape"
    elif source == "racing_api":
        cards = fetch_racing_api_racecards(day=day, region=region)
        src = "racing_api"
    else:
        cards = load_racecard_frames(day=day, region=region)
        src = "rpscrape"

    if cards.empty:
        raise RuntimeError("No runners in card window — check Racing API credentials or off times.")

    store_upcoming_runners(cards, source=src)
    odds, odds_meta = resolve_scoring_odds(cards, odds_source=odds_source)
    scored = score_upcoming_cards(cards, odds=odds if odds is not None and not odds.empty else None)

    paper_bets = 0
    if paper and "value_flag" in scored.columns:
        value = scored[scored["value_flag"] == 1]
        if not value.empty:
            stake = float(load_config().get("paper", {}).get("default_stake", 1.0))
            paper_bets = len(paper_log_value_picks(value, stake=stake))

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
    }
