from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

from hibs_racing.config import load_config
from hibs_racing.odds.matchbook import fetch_matchbook_odds
from hibs_racing.odds.oddschecker import fetch_oddschecker_odds, load_race_urls_file


def _matchbook_configured() -> bool:
    user = (os.environ.get("MATCHBOOK_USERNAME") or os.environ.get("MATCHBOOK_USER") or "").strip()
    return bool(user and os.environ.get("MATCHBOOK_PASSWORD", "").strip())


def _oddschecker_enabled(cfg: dict) -> bool:
    oc_cfg = cfg.get("oddschecker") or {}
    if not oc_cfg.get("enabled", True):
        return False
    if os.getenv("HIBS_DISABLE_ODDSCHECKER", "").strip().lower() in ("1", "true", "yes", "on"):
        return False
    if oc_cfg.get("auto_scrape", False):
        return True
    return os.getenv("HIBS_ODDS_AUTO_SCRAPE", "1").strip().lower() in ("1", "true", "yes", "on")


def _oddschecker_circuit_open() -> bool:
    try:
        from hibs_racing.scrapers.scrape_resilience import get_circuit

        allows, _ = get_circuit("oddschecker").allows_traffic()
        return not allows
    except Exception:
        return False


def _min_odds_coverage_ratio() -> float:
    try:
        return float(os.getenv("HIBS_RACING_ODDS_COVERAGE_MIN_PCT", "40")) / 100.0
    except ValueError:
        return 0.4


def _embedded_card_odds(cards: pd.DataFrame) -> pd.DataFrame | None:
    if "win_decimal" not in cards.columns:
        return None
    priced = cards.loc[cards["win_decimal"].notna()].copy()
    if priced.empty:
        return None
    priced = priced[priced["win_decimal"].astype(float) > 1.0]
    if priced.empty:
        return None
    cols = ["horse_name", "win_decimal"]
    if "runner_id" in priced.columns:
        cols = ["runner_id", *cols]
    return priced[cols].copy()


def _odds_coverage(odds: pd.DataFrame | None, *, card_runners: int) -> float:
    if card_runners <= 0:
        return 0.0
    if odds is None or odds.empty:
        return 0.0
    if "runner_id" in odds.columns:
        priced = int(odds["runner_id"].nunique())
    else:
        priced = len(odds)
    return priced / card_runners


def _merge_odds_frames(*frames: pd.DataFrame | None) -> pd.DataFrame | None:
    merged: pd.DataFrame | None = None
    for frame in frames:
        if frame is None or frame.empty:
            continue
        part = frame.copy()
        if merged is None:
            merged = part
            continue
        if "runner_id" in merged.columns and "runner_id" in part.columns:
            known = set(merged["runner_id"].astype(str))
            extra = part[~part["runner_id"].astype(str).isin(known)]
            if not extra.empty:
                merged = pd.concat([merged, extra], ignore_index=True)
        else:
            merged = pd.concat([merged, part], ignore_index=True)
    return merged


def _try_cached_exchange(cards: pd.DataFrame, *, meta: dict, prior_source: str) -> tuple[pd.DataFrame | None, dict]:
    from hibs_racing.odds.exchange_quotes import load_cached_exchange_odds

    odds = load_cached_exchange_odds(cards)
    if odds is None or odds.empty:
        return None, meta
    meta = dict(meta)
    meta["source"] = "exchange_cache"
    meta["rows"] = len(odds)
    meta["fallback_from"] = prior_source
    return odds, meta


def _try_oddschecker(
    cards: pd.DataFrame,
    *,
    config_path: Path | None,
    race_urls_file: str | Path | None,
    meta: dict,
    prior_source: str,
) -> tuple[pd.DataFrame | None, dict]:
    if not _oddschecker_enabled(load_config(config_path)):
        return None, meta
    if _oddschecker_circuit_open():
        meta = dict(meta)
        meta["oddschecker_attempt"] = {"errors": ["oddschecker circuit open (blocked)"]}
        return None, meta
    race_urls = load_race_urls_file(Path(race_urls_file)) if race_urls_file else {}
    odds, report = fetch_oddschecker_odds(cards, config_path=config_path, race_urls=race_urls)
    if odds is not None and not odds.empty:
        meta = dict(meta)
        meta["source"] = "oddschecker"
        meta["report"] = report.to_dict()
        meta["fallback_from"] = prior_source
        return odds, meta
    meta = dict(meta)
    meta["oddschecker_attempt"] = report.to_dict() if hasattr(report, "to_dict") else {}
    return None, meta


def _try_matchbook(
    cards: pd.DataFrame,
    *,
    config_path: Path | None,
    meta: dict,
    force: bool = False,
) -> tuple[pd.DataFrame | None, dict]:
    from hibs_racing.matchbook_guard import matchbook_traffic_allowed

    if not _matchbook_configured():
        meta = dict(meta)
        meta["matchbook_attempt"] = {"errors": ["matchbook not configured"]}
        return None, meta
    if not matchbook_traffic_allowed(force=force):
        meta = dict(meta)
        meta["matchbook_attempt"] = {"errors": ["matchbook poll gated"]}
        return None, meta
    odds, report = fetch_matchbook_odds(cards, config_path=config_path, force=force)
    meta = dict(meta)
    meta["source"] = "matchbook"
    meta["report"] = report.to_dict()
    meta["runners_priced"] = getattr(report, "runners_priced", None) or report.to_dict().get("runners_priced")
    return (odds if odds is not None and not odds.empty else None), meta


def _auto_cascade(
    cards: pd.DataFrame,
    *,
    config_path: Path | None,
    race_urls_file: str | Path | None,
    meta: dict,
    force_live_odds: bool = False,
) -> tuple[pd.DataFrame | None, dict]:
    """embedded → matchbook → oddschecker → exchange cache; merge partial layers."""
    cfg = load_config(config_path)
    mb_cfg = cfg.get("matchbook", {})
    card_n = max(len(cards), 1)
    min_cov = _min_odds_coverage_ratio()
    parts: list[pd.DataFrame] = []
    sources: list[str] = []

    embedded = _embedded_card_odds(cards)
    if embedded is not None:
        parts.append(embedded)
        sources.append("card_embedded")

    merged = _merge_odds_frames(*parts)
    cov = _odds_coverage(merged, card_runners=card_n)
    if cov < min_cov and mb_cfg.get("enabled", True) and mb_cfg.get("auto_fetch", True) and _matchbook_configured():
        try:
            mb_odds, meta = _try_matchbook(cards, config_path=config_path, meta=meta, force=force_live_odds)
            if mb_odds is not None:
                parts.append(mb_odds)
                sources.append("matchbook")
                merged = _merge_odds_frames(*parts)
        except Exception as exc:
            meta = dict(meta)
            meta["matchbook_attempt"] = {"error": str(exc)[:120]}

    cov = _odds_coverage(merged, card_runners=card_n)
    if cov < min_cov:
        oc_odds, meta = _try_oddschecker(
            cards, config_path=config_path, race_urls_file=race_urls_file, meta=meta, prior_source="auto"
        )
        if oc_odds is not None:
            parts.append(oc_odds)
            sources.append("oddschecker")
            merged = _merge_odds_frames(*parts)

    cov = _odds_coverage(merged, card_runners=card_n)
    if cov < min_cov:
        cached, meta = _try_cached_exchange(cards, meta=meta, prior_source="auto")
        if cached is not None:
            parts.append(cached)
            sources.append("exchange_cache")
            merged = _merge_odds_frames(*parts)

    if merged is None or merged.empty:
        meta = dict(meta)
        meta["source"] = "none"
        meta["coverage_ratio"] = 0.0
        return None, meta

    meta = dict(meta)
    meta["source"] = "+".join(sources) if len(sources) > 1 else (sources[0] if sources else "mixed")
    meta["layers"] = sources
    meta["rows"] = len(merged)
    meta["coverage_ratio"] = round(_odds_coverage(merged, card_runners=card_n), 4)
    return merged, meta


def resolve_scoring_odds(
    cards: pd.DataFrame,
    *,
    odds_csv: str | Path | None = None,
    odds_source: str | None = None,
    race_urls_file: str | Path | None = None,
    config_path: Path | None = None,
    force_live_odds: bool = False,
) -> tuple[pd.DataFrame | None, dict]:
    """
    Resolve odds for score-card: csv | matchbook | oddschecker | embedded card prices.

    Cascade (auto / matchbook modes): embedded → matchbook → oddschecker scrape → exchange cache → none.
    Returns (odds_df_or_none, meta_dict).
    """
    cfg = load_config(config_path)
    mb_cfg = cfg.get("matchbook", {})
    oc_cfg = cfg.get("oddschecker", {})
    source = (odds_source or os.getenv("HIBS_ODDS_SOURCE") or oc_cfg.get("default_source") or mb_cfg.get("default_source") or "auto").lower()
    meta: dict = {"source": source, "requested_source": source}
    force = force_live_odds or os.getenv("HIBS_MATCHBOOK_FORCE_POLL", "").strip().lower() in ("1", "true", "yes", "on")

    if odds_csv:
        odds = pd.read_csv(odds_csv)
        meta["source"] = "csv"
        meta["rows"] = len(odds)
        return odds, meta

    embedded = _embedded_card_odds(cards)

    if source in ("oddschecker", "oc"):
        odds, meta = _try_oddschecker(
            cards, config_path=config_path, race_urls_file=race_urls_file, meta=meta, prior_source=source
        )
        if odds is not None:
            return odds, meta
        if embedded is not None:
            meta["source"] = "card_embedded"
            meta["fallback_from"] = "oddschecker"
            return embedded, meta
        cached, meta = _try_cached_exchange(cards, meta=meta, prior_source="oddschecker")
        if cached is not None:
            return cached, meta
        meta["source"] = "none"
        return None, meta

    if source in ("matchbook", "mb", "exchange"):
        odds, meta = _try_matchbook(cards, config_path=config_path, meta=meta, force=force)
        if odds is not None:
            return odds, meta
        odds, meta = _try_oddschecker(
            cards, config_path=config_path, race_urls_file=race_urls_file, meta=meta, prior_source="matchbook"
        )
        if odds is not None:
            return odds, meta
        if embedded is not None:
            meta["source"] = "card_embedded"
            meta["fallback_from"] = "matchbook"
            return embedded, meta
        cached, meta = _try_cached_exchange(cards, meta=meta, prior_source="matchbook")
        if cached is not None:
            return cached, meta
        meta["source"] = "none"
        return None, meta

    if source == "auto":
        return _auto_cascade(
            cards,
            config_path=config_path,
            race_urls_file=race_urls_file,
            meta=meta,
            force_live_odds=force,
        )

    if source in ("card_embedded", "embedded"):
        if embedded is not None:
            meta["source"] = "card_embedded"
            meta["rows"] = len(embedded)
            return embedded, meta
        meta["source"] = "none"
        return None, meta

    if source == "none":
        return None, meta

    raise ValueError(f"Unknown odds_source: {source}")
