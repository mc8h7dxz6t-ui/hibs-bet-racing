"""Scrape-first mode when Racing API creds are missing or blocked."""

from __future__ import annotations

import os
from typing import Any, Dict


def _truthy(name: str) -> bool:
    return (os.getenv(name) or "").strip().lower() in ("1", "true", "yes", "on")


def racing_api_configured() -> bool:
    user = (os.getenv("RACING_API_USERNAME") or "").strip()
    pwd = (os.getenv("RACING_API_PASSWORD") or "").strip()
    return bool(user and pwd)


def scrape_first_mode() -> bool:
    if _truthy("HIBS_DISABLE_RACING_API"):
        return True
    if _truthy("HIBS_RACING_SCRAPE_FIRST"):
        return True
    try:
        from hibs_racing.racing_api_guard import global_trip_active

        if global_trip_active():
            return True
    except Exception:
        pass
    return not racing_api_configured()


def default_cards_source() -> str:
    if scrape_first_mode():
        return (os.getenv("HIBS_RACING_SCRAPE_SOURCE") or "rpscrape").strip() or "rpscrape"
    return "racing_api"


def scrape_first_status() -> Dict[str, Any]:
    active = scrape_first_mode()
    reason = "api_configured"
    if _truthy("HIBS_DISABLE_RACING_API"):
        reason = "HIBS_DISABLE_RACING_API"
    elif _truthy("HIBS_RACING_SCRAPE_FIRST"):
        reason = "HIBS_RACING_SCRAPE_FIRST"
    elif not racing_api_configured():
        reason = "missing_credentials"
    else:
        try:
            from hibs_racing.racing_api_guard import global_trip_active

            if global_trip_active():
                reason = "api_guard_trip"
        except Exception:
            pass
    return {
        "scrape_first": active,
        "reason": reason,
        "api_configured": racing_api_configured(),
        "default_cards_source": default_cards_source(),
    }
