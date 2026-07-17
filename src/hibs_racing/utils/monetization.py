"""Racing monetization venue registry — Matchbook-first exchange + affiliate chain."""

from __future__ import annotations

import os
import urllib.parse
from typing import Any

AFFILIATE_BASE_URLS: dict[str, str] = {
    "matchbook": "https://www.matchbook.com/",
    "betfair": "https://www.betfair.com/exchange/plus/horse-racing/",
    "smarkets": "https://smarkets.com/event/horse-racing",
    "betdaq": "https://www.betdaq.com/exchange/horse-racing",
    "oddschecker": "https://www.oddschecker.com/horse-racing/",
}

PLATFORM_VENUE_ORDER: tuple[str, ...] = ("matchbook", "betfair", "smarkets", "betdaq")

VENUE_COMMISSION_BPS: dict[str, float] = {
    "matchbook": 200.0,
    "betfair": 250.0,
    "smarkets": 200.0,
    "betdaq": 225.0,
}


def _env_truthy(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def betfair_credentials_present() -> bool:
    return bool(
        os.environ.get("BETFAIR_APP_KEY", "").strip()
        and os.environ.get("BETFAIR_USERNAME", "").strip()
        and os.environ.get("BETFAIR_PASSWORD", "").strip()
    )


def betfair_monetization_armed() -> bool:
    if not _env_truthy("HIBS_BETFAIR_MONETIZATION_ENABLED"):
        return False
    return betfair_credentials_present()


def venue_enabled(venue: str) -> bool:
    key = (venue or "").strip().lower()
    if key == "matchbook":
        return True
    if key in ("smarkets", "betdaq", "oddschecker"):
        return True
    if key == "betfair":
        return betfair_monetization_armed()
    return False


def venue_status(venue: str) -> dict[str, Any]:
    key = (venue or "").strip().lower()
    enabled = venue_enabled(key)
    reason = "active"
    if not enabled and key == "betfair":
        if not _env_truthy("HIBS_BETFAIR_MONETIZATION_ENABLED"):
            reason = "awaiting_enable_flag"
        elif not betfair_credentials_present():
            reason = "awaiting_credentials"
        else:
            reason = "disabled"
    return {
        "id": key,
        "label": key.title(),
        "enabled": enabled,
        "reason": reason,
        "commission_bps": VENUE_COMMISSION_BPS.get(key),
        "affiliate_base_url": affiliate_base_url(key),
    }


def active_venues() -> list[str]:
    return [v for v in PLATFORM_VENUE_ORDER if venue_enabled(v)]


def default_affiliate_venue() -> str:
    raw = os.environ.get("HIBS_AFFILIATE_VENUE", "").strip().lower()
    if raw and venue_enabled(raw):
        return raw
    active = active_venues()
    return active[0] if active else "matchbook"


def affiliate_base_url(venue: str = "matchbook") -> str:
    env_key = f"AFFILIATE_{venue.upper()}_BASE_URL"
    custom = os.environ.get(env_key, "").strip()
    if custom:
        return custom.rstrip("/") + "/"
    return AFFILIATE_BASE_URLS.get(venue, AFFILIATE_BASE_URLS["matchbook"])


def routing_channels() -> tuple[str, ...]:
    channels = [v for v in active_venues() if v in VENUE_COMMISSION_BPS]
    return tuple(channels) if channels else ("matchbook",)


def commission_by_channel() -> dict[str, float]:
    return {k: VENUE_COMMISSION_BPS[k] for k in routing_channels() if k in VENUE_COMMISSION_BPS}


def public_monetization_payload() -> dict[str, Any]:
    venues = [venue_status(v) for v in PLATFORM_VENUE_ORDER]
    return {
        "platform": "racing",
        "monetization_primary_venue": default_affiliate_venue(),
        "monetization_venues": venues,
        "monetization_active_venues": active_venues(),
        "monetization_routing_channels": list(routing_channels()),
        "betfair_monetization_armed": betfair_monetization_armed(),
    }


def generate_monetized_link(
    runner_name: str,
    course: str,
    off_time: str,
    *,
    venue: str | None = None,
    utm_medium: str = "premium_daily_sheet",
) -> str:
    """Wrap partner base URL with UTM + race context for trackable affiliate redirects."""
    book = venue or default_affiliate_venue()
    if not venue_enabled(book):
        book = default_affiliate_venue()
    base_url = affiliate_base_url(book).rstrip("/")
    params = {
        "utm_source": os.environ.get("HIBS_AFFILIATE_UTM_SOURCE", "hibs_racing_app").strip() or "hibs_racing_app",
        "utm_medium": utm_medium,
        "event_ref": f"{course}_{off_time}".lower().replace(" ", "_"),
        "selection": runner_name,
    }
    tracking_id = os.environ.get("HIBS_AFFILIATE_TRACKING_ID", "").strip()
    if tracking_id:
        params["affiliate_id"] = tracking_id
    sep = "&" if "?" in base_url else "?"
    return f"{base_url}{sep}{urllib.parse.urlencode(params)}"


def attach_monetized_links(
    picks: list[dict],
    *,
    venue: str | None = None,
    utm_medium: str = "premium_daily_sheet",
) -> list[dict]:
    """Add monetized_link to pick dicts (UI / API layer only)."""
    book = venue or default_affiliate_venue()
    out: list[dict] = []
    for pick in picks:
        link = generate_monetized_link(
            str(pick.get("horse_name") or ""),
            str(pick.get("course") or ""),
            str(pick.get("off_time") or ""),
            venue=book,
            utm_medium=utm_medium,
        )
        out.append({**pick, "monetized_link": link, "monetization_venue": book})
    return out
