"""Racing merge into shared ingest spine (hibs-bet spine_store)."""

from __future__ import annotations

from typing import Any, Dict, List, Sequence

from hibs_racing.scrapers.multi_scraper_api import FIELD_LADDERS


def merge_racing_fields(
    entity_keys: Sequence[str],
    field_ladders: Dict[str, List[str]] | None = None,
) -> Dict[str, Any]:
    """Merge racing field_snapshots using FIELD_LADDERS."""
    from hibs_predictor.ingest.spine_store import merge_all_for_sport

    ladders = field_ladders or FIELD_LADDERS
    return merge_all_for_sport("racing", entity_keys, ladders)
