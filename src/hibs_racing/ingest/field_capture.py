"""Capture racing scored-card rows into field_snapshots (Layer 3)."""

from __future__ import annotations

from typing import Any, Dict, List, Sequence

from hibs_racing.scrapers.multi_scraper_api import FIELD_LADDERS


def _runner_key(row: Dict[str, Any]) -> str:
    rid = row.get("runner_id")
    if rid:
        return str(rid).strip()
    rnk = row.get("race_natural_key")
    horse = row.get("horse_name") or row.get("horse")
    if rnk and horse:
        return f"{rnk}|{horse}"
    return ""


def _source_tag(row: Dict[str, Any], field_name: str) -> str:
    base = str(row.get("source") or row.get("enrich_source") or "racing_api")
    if field_name == "win_odds":
        return base
    if field_name == "model_score":
        return str(row.get("scoring_method") or "card_scores")
    if field_name == "place_probs":
        return "card_scores"
    if field_name == "jockey_trainer":
        return base
    if field_name == "official_rating":
        return base
    if field_name == "enrich_form":
        return str(row.get("enrich_source") or "racing_post_scrape")
    if field_name == "card_comment":
        return base
    return "bundle"


def _field_payload(row: Dict[str, Any], field_name: str) -> Dict[str, Any]:
    if field_name == "win_odds":
        return {"win_decimal": row.get("win_decimal")}
    if field_name == "model_score":
        return {
            "model_score": row.get("model_score"),
            "model_win_prob": row.get("model_win_prob"),
            "scoring_method": row.get("scoring_method"),
        }
    if field_name == "place_probs":
        return {
            "model_place_prob": row.get("model_place_prob"),
            "combo_bayes_place": row.get("combo_bayes_place"),
            "offered_place_decimal": row.get("offered_place_decimal"),
        }
    if field_name == "jockey_trainer":
        return {"jockey": row.get("jockey"), "trainer": row.get("trainer")}
    if field_name == "official_rating":
        return {
            "official_rating": row.get("official_rating"),
            "rpr": row.get("rpr"),
        }
    if field_name == "enrich_form":
        return {
            "form_string": row.get("form_string"),
            "days_since_last_run": row.get("days_since_last_run"),
            "rp_verdict": row.get("rp_verdict"),
        }
    if field_name == "card_comment":
        return {"card_comment": row.get("card_comment")}
    return {}


def _rows_from_runners(runners: Sequence[Dict[str, Any]] | None) -> List[Dict[str, Any]]:
    if runners is not None:
        return [dict(r) for r in runners if isinstance(r, dict)]
    from hibs_racing.cards.query import load_scored_cards

    frame = load_scored_cards()
    if frame.empty:
        return []
    return frame.to_dict(orient="records")


def capture_racing_field_snapshots(
    runners: Sequence[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    """Upsert field_snapshots for each runner × ladder field present on the row."""
    from hibs_predictor.ingest.spine_store import upsert_field_snapshot

    rows = _rows_from_runners(runners)
    written = 0
    skipped = 0
    keys: List[str] = []
    for row in rows:
        key = _runner_key(row)
        if not key:
            skipped += 1
            continue
        keys.append(key)
        for field_name in FIELD_LADDERS:
            payload = _field_payload(row, field_name)
            source = _source_tag(row, field_name)
            if upsert_field_snapshot(
                sport="racing",
                entity_type="runner",
                natural_key=key,
                field_name=field_name,
                source_tag=source,
                payload=payload,
            ):
                written += 1
            else:
                skipped += 1
    return {
        "written": written,
        "skipped": skipped,
        "runner_count": len(keys),
        "runner_keys": keys,
    }
