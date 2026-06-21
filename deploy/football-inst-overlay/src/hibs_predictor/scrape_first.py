"""Scrape-first mode when API-Sports is disabled or no usable key is configured."""

from __future__ import annotations

import os


def _truthy(name: str) -> bool:
    return (os.getenv(name) or "").strip().lower() in ("1", "true", "yes", "on")


def _env_first_usable(*names: str) -> str:
    for name in names:
        val = (os.getenv(name) or "").strip()
        if len(val) >= 16:
            return val
    return ""


def api_sports_explicitly_disabled() -> bool:
    return _truthy("HIBS_DISABLE_API_SPORTS")


def usable_api_sports_key() -> str:
    return _env_first_usable(
        "API_SPORTS_FOOTBALL_KEY",
        "API_SPORTS_KEY",
        "APISPORTS_KEY",
    )


def scrape_first_mode() -> bool:
    """True when fixtures/enrich should not rely on API-Sports."""
    if api_sports_explicitly_disabled():
        return True
    return not bool(usable_api_sports_key())


def fixture_fetch_flags() -> tuple[bool, bool]:
    """(prefer_football_data, skip_api_sports) — scrape-first when API off."""
    prefer = _truthy("HIBS_PREFER_FOOTBALL_DATA_FIXTURES") or scrape_first_mode()
    skip = _truthy("HIBS_SKIP_API_SPORTS_FIXTURES") or scrape_first_mode()
    return prefer, skip


def skip_api_injuries() -> bool:
    """When true, injury_hint ladder uses scrapers (e.g. FPL) instead of API-Sports."""
    return _truthy("HIBS_SKIP_API_INJURIES") or scrape_first_mode()


def scrape_first_status() -> dict[str, object]:
    key = usable_api_sports_key()
    active = scrape_first_mode()
    reason = "explicit_disable" if api_sports_explicitly_disabled() else (
        "no_api_key" if not key else "api_sports_available"
    )
    return {
        "scrape_first": active,
        "reason": reason,
        "api_key_configured": bool(key),
    }
