"""Scrape-first mode when Racing API creds are missing."""

from __future__ import annotations

import os


def _truthy(name: str) -> bool:
    return (os.getenv(name) or "").strip().lower() in ("1", "true", "yes", "on")


def racing_api_configured() -> bool:
    user = (os.getenv("RACING_API_USERNAME") or "").strip()
    pwd = (os.getenv("RACING_API_PASSWORD") or "").strip()
    return bool(user and pwd)


def scrape_first_mode() -> bool:
    if _truthy("HIBS_DISABLE_RACING_API"):
        return True
    return not racing_api_configured()


def default_cards_source() -> str:
    if scrape_first_mode():
        return (os.getenv("HIBS_RACING_SCRAPE_SOURCE") or "rpscrape").strip() or "rpscrape"
    return (os.getenv("HIBS_ODDS_SOURCE") or "racing_api").strip() or "racing_api"
