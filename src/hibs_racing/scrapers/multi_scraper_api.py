"""
Racing field-level provider catalog — mirrors football multi_scraper_api.FIELD_LADDERS.

Read-only registry for short-data rescue and /api/runner field resolution.
No network I/O in this module.
"""

from __future__ import annotations

from typing import Any, Dict, List

FIELD_LADDERS: Dict[str, List[str]] = {
    "win_odds": [
        "racing_api",
        "matchbook",
        "retail_scrape",
        "betfair_exchange",
    ],
    "model_score": [
        "lgbm_ranker",
        "card_scores",
    ],
    "place_probs": [
        "harville",
        "card_scores",
    ],
    "jockey_trainer": [
        "racing_api",
        "racing_post_scrape",
    ],
    "official_rating": [
        "racing_api",
        "racing_post_scrape",
        "raceform_db",
    ],
    "enrich_form": [
        "racing_post_scrape",
        "rp_verdict",
        "raceform_db",
        "dense_field_repair",
    ],
    "card_comment": [
        "racing_api",
        "racing_post_scrape",
    ],
}

TARGETED_OVERFLOW: List[Dict[str, Any]] = [
    {
        "id": "racing_post_scrape",
        "label": "Racing Post racecards",
        "fields": ("enrich_form", "official_rating", "card_comment"),
        "env_enable": ("EMAIL", "ACCESS_TOKEN"),
        "notes": "RP enrich spine; batch via refresh-cards.",
    },
    {
        "id": "matchbook",
        "label": "Matchbook session API",
        "fields": ("win_odds",),
        "env_enable": ("MATCHBOOK_USERNAME", "MATCHBOOK_PASSWORD"),
        "notes": "Best back price per runner when credentialed.",
    },
    {
        "id": "raceform_db",
        "label": "Local raceform SQLite",
        "fields": ("enrich_form", "official_rating"),
        "env_enable": ("RACEFORM_DB_PATH",),
        "notes": "Offline historical enrich backfill.",
    },
]


def catalog_summary() -> Dict[str, Any]:
    return {
        "product": "hibs-racing",
        "field_ladders": FIELD_LADDERS,
        "targeted_overflow": TARGETED_OVERFLOW,
    }
