"""
Targeted multi-scraper field resolver catalog.

Central registry for field-level provider ladders (settlement, xG, form).
Providers are wired incrementally — FT backups and EPL FPL supplement first.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

# field → ordered provider ids
FIELD_LADDERS: Dict[str, List[str]] = {
    "ft_result": [
        "api_sports",
        "football_data_org",
        "fotmob_calendar",
        "fotmob_calendar_adjacent",
        "espn_scoreboard",
        "sofascore_events",
    ],
    "team_xg": [
        "api_fixture_xg",
        "understat",
        "fotmob_league_xg",
        "fpl_api",
        "statsbomb_goals_proxy",
        "goals_proxy",
    ],
    "recent_form": [
        "api_sports",
        "football_data_org",
        "fotmob_calendar",
        "fpl_fixtures",
    ],
    "standings": [
        "api_sports",
        "football_data_org",
        "soccerstats",
        "fotmob_league",
        "fpl_table",
    ],
    "injury_hint": [
        "api_sports",
        "fpl_availability",
    ],
}

TARGETED_OVERFLOW: List[Dict[str, Any]] = [
    {
        "id": "espn_scoreboard",
        "label": "ESPN scoreboard",
        "leagues": "Mapped cups + domestic (see espn_client.ESPN_LEAGUE_SLUG)",
        "fields": ("ft_result",),
        "env_enable": ("HIBS_SETTLE_BACKUP_ESPN",),
        "notes": "Public JSON; strong for WC/UCL when FotMob lags.",
    },
    {
        "id": "fpl_api",
        "label": "Fantasy Premier League API",
        "leagues": "EPL only",
        "fields": ("team_xg", "recent_form", "standings", "injury_hint"),
        "env_enable": ("HIBS_ENABLE_FPL_EPL", "HIBS_MAX_DATA"),
        "notes": "bootstrap-static + fixtures; no key.",
    },
]


def catalog_summary() -> Dict[str, Any]:
    return {
        "field_ladders": FIELD_LADDERS,
        "targeted_overflow": TARGETED_OVERFLOW,
    }


def resolve_ft_backup(
    row: Any,
    *,
    scrape_cache: Optional[Dict[str, Any]] = None,
) -> Tuple[Optional[int], Optional[Dict[str, Any]], str, str]:
    """Walk ``ft_result`` ladder (scrapers after API) — settlement cold path only."""
    from hibs_predictor.scrapers.settlement_ft_backups import resolve_ft_from_backup_scrapers

    return resolve_ft_from_backup_scrapers(row, scrape_cache=scrape_cache)


def resolve_field(
    field: str,
    row: Any,
    clients: Dict[str, Any],
    *,
    scrape_cache: Optional[Dict[str, Any]] = None,
) -> Tuple[Optional[int], Optional[Dict[str, Any]], str, str]:
    """Dispatch field-level resolver using ``FIELD_LADDERS`` catalog."""
    if field == "ft_result":
        from hibs_predictor.audit_settlement_resolvers import resolve_ft_from_scrape_fallback

        return resolve_ft_from_scrape_fallback(row, clients, scrape_cache=scrape_cache)
    if field in FIELD_LADDERS:
        return None, None, f"no_resolver_for_{field}", ""
    return None, None, "unknown_field", ""
