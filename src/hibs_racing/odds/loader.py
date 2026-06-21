from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

from hibs_racing.config import load_config
from hibs_racing.odds.matchbook import fetch_matchbook_odds
from hibs_racing.odds.oddschecker import fetch_oddschecker_odds, load_race_urls_file


def _matchbook_configured() -> bool:
    return bool(os.environ.get("MATCHBOOK_USERNAME", "").strip() and os.environ.get("MATCHBOOK_PASSWORD", "").strip())


def resolve_scoring_odds(
    cards: pd.DataFrame,
    *,
    odds_csv: str | Path | None = None,
    odds_source: str | None = None,
    race_urls_file: str | Path | None = None,
    config_path: Path | None = None,
) -> tuple[pd.DataFrame | None, dict]:
    """
    Resolve odds for score-card: csv | matchbook | oddschecker | embedded card prices.
    Returns (odds_df_or_none, meta_dict).
    """
    cfg = load_config(config_path)
    mb_cfg = cfg.get("matchbook", {})
    oc_cfg = cfg.get("oddschecker", {})
    source = (odds_source or oc_cfg.get("default_source") or mb_cfg.get("default_source") or "auto").lower()
    meta: dict = {"source": source}

    if odds_csv:
        odds = pd.read_csv(odds_csv)
        meta["source"] = "csv"
        meta["rows"] = len(odds)
        return odds, meta

    if source in ("matchbook", "mb", "exchange"):
        odds, report = fetch_matchbook_odds(cards, config_path=config_path)
        meta["source"] = "matchbook"
        meta["report"] = report.to_dict()
        meta["runners_priced"] = getattr(report, "runners_priced", None) or (report.to_dict().get("runners_priced"))
        return odds if not odds.empty else None, meta

    if source in ("oddschecker", "oc"):
        race_urls = load_race_urls_file(Path(race_urls_file)) if race_urls_file else {}
        odds, report = fetch_oddschecker_odds(cards, config_path=config_path, race_urls=race_urls)
        meta["source"] = "oddschecker"
        meta["report"] = report.to_dict()
        return odds if not odds.empty else None, meta

    if source == "auto":
        if "win_decimal" in cards.columns and cards["win_decimal"].notna().any():
            odds = cards.loc[cards["win_decimal"].notna(), ["horse_name", "win_decimal"]].copy()
            meta["source"] = "card_embedded"
            meta["rows"] = len(odds)
            return odds, meta
        if mb_cfg.get("enabled", True) and _matchbook_configured() and mb_cfg.get("auto_fetch", True):
            try:
                odds, report = fetch_matchbook_odds(cards, config_path=config_path)
                if not odds.empty:
                    meta["source"] = "matchbook"
                    meta["report"] = report.to_dict()
                    return odds, meta
                meta["matchbook_attempt"] = report.to_dict()
            except Exception as exc:
                meta["matchbook_attempt"] = {"error": str(exc)[:120]}
        if oc_cfg.get("auto_scrape", False) or os.getenv("HIBS_ODDS_AUTO_SCRAPE", "").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        ):
            odds, report = fetch_oddschecker_odds(cards, config_path=config_path)
            meta["source"] = "oddschecker"
            meta["report"] = report.to_dict()
            return odds if not odds.empty else None, meta
        meta["source"] = "none"
        return None, meta

    if source == "none":
        return None, meta

    raise ValueError(f"Unknown odds_source: {source}")
