"""Affiliate / partner link routing for novice UX (slip copy, odds badges)."""

from __future__ import annotations

import os
import urllib.parse

AFFILIATE_CONFIG: dict[str, str] = {
    "matchbook": "https://www.matchbook.com/",
    "betfair": "https://www.betfair.com/exchange/plus/horse-racing/",
    "oddschecker": "https://www.oddschecker.com/horse-racing/",
}


def default_affiliate_venue() -> str:
    raw = os.environ.get("HIBS_AFFILIATE_VENUE", "matchbook").strip().lower()
    return raw if raw in AFFILIATE_CONFIG else "matchbook"


def affiliate_base_url(venue: str = "matchbook") -> str:
    env_key = f"AFFILIATE_{venue.upper()}_BASE_URL"
    custom = os.environ.get(env_key, "").strip()
    if custom:
        return custom.rstrip("/") + "/"
    return AFFILIATE_CONFIG.get(venue, AFFILIATE_CONFIG["matchbook"])


def generate_monetized_link(
    runner_name: str,
    course: str,
    off_time: str,
    *,
    venue: str | None = None,
    utm_medium: str = "premium_daily_sheet",
) -> str:
    """
    Wrap partner base URL with UTM + race context for trackable affiliate redirects.
    """
    book = venue or default_affiliate_venue()
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
        out.append({**pick, "monetized_link": link})
    return out
