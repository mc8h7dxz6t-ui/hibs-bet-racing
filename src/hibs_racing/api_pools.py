"""External API shared pools — who shares credentials and rate limits (racing)."""

from __future__ import annotations

from typing import Any, Dict, List

# Each pool: one credential set → one coordinated budget.
API_POOLS: Dict[str, Dict[str, Any]] = {
    "racing_post": {
        "credentials": ("EMAIL", "ACCESS_TOKEN"),
        "guard": "hibs_racing.ingest.rp_traffic_guard",
        "rate_controls": (
            "RP_SCRAPE_DAY_PAUSE_SEC",
            "RP_RACECARD_REGION_PAUSE_SEC",
            "RP_VERDICT_RACE_PAUSE_SEC",
            "HIBS_RP_MAX_CONCURRENT_LIVE",
            "HIBS_RP_TRIP_TTL_HOURS",
        ),
        "consumers": [
            "ingest.scrape (rpscrape day CSV)",
            "ingest.racecards (live racecards.py)",
            "cards.enrich.dual_source_enrich",
            "ingest.rp_verdict",
            "scrapers.field_resolver thin rescue",
            "ingest.historical_racecards",
        ],
    },
    "the_racing_api": {
        "credentials": ("RACING_API_USERNAME", "RACING_API_PASSWORD"),
        "guard": "hibs_racing.racing_api_guard",
        "rate_controls": (
            "RACING_API_PAUSE_SEC",
            "RACING_API_429_PAUSE_SEC",
            "HIBS_RACING_API_GLOBAL_TRIP_AFTER",
            "HIBS_RACING_API_FORBIDDEN_TTL_HOURS",
        ),
        "consumers": [
            "ingest.racing_api (cards + embedded odds)",
            "cards.refresh (api-first path)",
            "scrapers.field_resolver win_odds ladder",
        ],
    },
    "matchbook": {
        "credentials": ("MATCHBOOK_USERNAME", "MATCHBOOK_PASSWORD"),
        "guard": "hibs_racing.matchbook_guard",
        "rate_controls": (
            "matchbook.poll_seconds (config)",
            "HIBS_MATCHBOOK_TRIP_TTL_HOURS",
            "HIBS_MATCHBOOK_POLL_OWNER",
        ),
        "consumers": [
            "odds.matchbook REST poll",
            "odds.loader scoring cascade",
            "scrapers.field_resolver win_odds",
        ],
    },
    "oddschecker": {
        "credentials": (),
        "guard": "hibs_racing.scrapers.scrape_resilience (IP circuit)",
        "rate_controls": ("oddschecker.request_pause_sec", "HIBS_ODDSCHECKER_403_OPEN_SEC"),
        "consumers": ("odds.oddschecker retail scrape", "odds.loader fallback"),
    },
}


def all_pool_status() -> Dict[str, Any]:
    """Live status for ops / scrape status payload."""
    out: Dict[str, Any] = {}
    try:
        from hibs_racing.ingest.rp_traffic_guard import status_payload as rp_status

        out["racing_post"] = rp_status()
    except Exception as exc:
        out["racing_post"] = {"error": str(exc)[:120]}
    try:
        from hibs_racing.racing_api_guard import status_payload as tra_status

        out["the_racing_api"] = tra_status()
    except Exception as exc:
        out["the_racing_api"] = {"error": str(exc)[:120]}
    try:
        from hibs_racing.matchbook_guard import status_payload as mb_status

        out["matchbook"] = mb_status()
    except Exception as exc:
        out["matchbook"] = {"error": str(exc)[:120]}
    out["pools"] = {k: {"credentials": v["credentials"], "consumers": v["consumers"]} for k, v in API_POOLS.items()}
    return out
