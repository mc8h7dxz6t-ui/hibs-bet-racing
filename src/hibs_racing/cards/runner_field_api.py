"""Fast per-runner field payload for institutional short-data APIs."""

from __future__ import annotations

from typing import Any, Dict, Optional

import pandas as pd

from hibs_racing.cards.data_quality import runner_data_quality_pct, runner_quality_blocks
from hibs_racing.cards.query import load_scored_cards
from hibs_racing.scrapers.multi_scraper_api import FIELD_LADDERS, catalog_summary


def _row_to_dict(row: pd.Series) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key, val in row.items():
        if isinstance(val, float) and pd.isna(val):
            out[key] = None
        elif pd.isna(val):
            out[key] = None
        else:
            out[key] = val
    return out


def load_runner_row(runner_id: str) -> Optional[Dict[str, Any]]:
    """Single-runner lookup from scored card frame (indexed in memory when hot)."""
    rid = (runner_id or "").strip()
    if not rid:
        return None
    frame = load_scored_cards()
    if frame.empty or "runner_id" not in frame.columns:
        return None
    hit = frame.loc[frame["runner_id"].astype(str) == rid]
    if hit.empty:
        return None
    return _row_to_dict(hit.iloc[0])


def resolve_runner_fields(runner_id: str, *, rescue: bool = False) -> Optional[Dict[str, Any]]:
    row = load_runner_row(runner_id)
    if not row:
        return None
    ladder_steps: Dict[str, Any] = {}
    if rescue:
        frame = load_scored_cards()
        race_id = row.get("race_id")
        race_slice = (
            frame.loc[frame["race_id"].astype(str) == str(race_id)]
            if race_id is not None and not frame.empty and "race_id" in frame.columns
            else frame.iloc[0:0]
        )
        from hibs_racing.scrapers.field_resolver import rescue_runner_fields

        rescued = rescue_runner_fields(row, race_slice=race_slice)
        row = rescued["row"]
        ladder_steps = rescued.get("ladder_steps") or {}
    blocks = runner_quality_blocks(row)
    payload = {
        "runner_id": row.get("runner_id"),
        "race_id": row.get("race_id"),
        "horse_name": row.get("horse_name"),
        "course": row.get("course"),
        "off_time": row.get("off_time"),
        "card_date": row.get("card_date"),
        "data_quality_pct": runner_data_quality_pct(row),
        "blocks": blocks,
        "field_ladders": FIELD_LADDERS,
        "fields": {k: row.get(k) for k in _public_field_keys()},
        "value_flag": row.get("value_flag"),
        "value_gate_reason": row.get("value_gate_reason"),
        "enrich_source": row.get("enrich_source"),
    }
    if ladder_steps:
        payload["rescued"] = True
        payload["ladder_steps"] = ladder_steps
    return payload


def _public_field_keys() -> tuple[str, ...]:
    return (
        "runner_id",
        "race_id",
        "horse_name",
        "win_decimal",
        "model_win_prob",
        "model_place_prob",
        "combo_bayes_place",
        "place_ev",
        "ew_combined_ev",
        "official_rating",
        "jockey",
        "trainer",
        "card_comment",
        "form_string",
        "horse_course_win_rate",
        "horse_distance_win_rate",
        "trainer_rtf",
        "form_lto_position",
        "model_score",
        "scoring_method",
    )


def scraper_catalog_payload() -> Dict[str, Any]:
    return catalog_summary()
