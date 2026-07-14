"""Field-level scraper ladder dispatch for racing — opt-in rescue only."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from hibs_racing.scrapers.multi_scraper_api import FIELD_LADDERS


def _is_missing(val: Any) -> bool:
    if val is None:
        return True
    try:
        if pd.isna(val):
            return True
    except (TypeError, ValueError):
        pass
    if isinstance(val, str) and not val.strip():
        return True
    return False


def _resolve_win_odds(race_slice: pd.DataFrame, row: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    updates: Dict[str, Any] = {}
    steps: List[str] = []
    if not _is_missing(row.get("win_decimal")):
        return updates, steps
    if race_slice.empty:
        return updates, steps
    from hibs_racing.odds.loader import resolve_scoring_odds

    odds_df, meta = resolve_scoring_odds(race_slice.copy())
    source = str(meta.get("source") or "")
    if source:
        steps.append(source)
    if odds_df is None or odds_df.empty:
        return updates, steps
    horse = str(row.get("horse_name") or "").strip()
    if not horse or "horse_name" not in odds_df.columns:
        return updates, steps
    hit = odds_df.loc[odds_df["horse_name"].astype(str).str.casefold() == horse.casefold()]
    if hit.empty:
        return updates, steps
    price = hit.iloc[0].get("win_decimal")
    if not _is_missing(price):
        updates["win_decimal"] = float(price)
    return updates, steps


def _resolve_enrich_form(race_slice: pd.DataFrame, row: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    updates: Dict[str, Any] = {}
    steps: List[str] = []
    need = any(_is_missing(row.get(k)) for k in ("form_string", "card_comment", "official_rating"))
    if not need or race_slice.empty:
        return updates, steps
    from hibs_racing.cards.enrich import dual_source_enrich

    enriched, meta = dual_source_enrich(race_slice.copy())
    steps.append(str(meta.get("source") or "dual_source_enrich"))
    horse = str(row.get("horse_name") or "").strip()
    if not horse or "horse_name" not in enriched.columns:
        return updates, steps
    hit = enriched.loc[enriched["horse_name"].astype(str).str.casefold() == horse.casefold()]
    if hit.empty:
        return updates, steps
    src_row = hit.iloc[0]
    for key in ("form_string", "card_comment", "official_rating", "jockey", "trainer"):
        if _is_missing(row.get(key)) and not _is_missing(src_row.get(key)):
            updates[key] = src_row.get(key)
    return updates, steps


_FIELD_RESOLVERS = {
    "win_odds": lambda race_slice, row: _resolve_win_odds(race_slice, row),
    "enrich_form": lambda race_slice, row: _resolve_enrich_form(race_slice, row),
    "official_rating": lambda race_slice, row: _resolve_enrich_form(race_slice, row),
    "card_comment": lambda race_slice, row: _resolve_enrich_form(race_slice, row),
    "jockey_trainer": lambda race_slice, row: _resolve_enrich_form(race_slice, row),
}


def rescue_runner_fields(row: Dict[str, Any], *, race_slice: pd.DataFrame) -> Dict[str, Any]:
    """Walk ``FIELD_LADDERS`` for null fields — only when ``?rescue=1``."""
    merged = dict(row)
    ladder_steps: Dict[str, List[str]] = {}
    for field, providers in FIELD_LADDERS.items():
        resolver = _FIELD_RESOLVERS.get(field)
        if resolver is None:
            continue
        updates, steps = resolver(race_slice, merged)
        if updates:
            merged.update(updates)
            ladder_steps[field] = steps or list(providers[:1])
    return {"row": merged, "ladder_steps": ladder_steps}
