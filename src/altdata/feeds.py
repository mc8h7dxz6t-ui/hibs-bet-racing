"""Production feed registry — real HTTP URLs with JSON field mapping."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

# Frankfurter FX API — free, no API key, stable for demos and design partners.
_DEFAULT_FX_URL = "https://api.frankfurter.app/latest?from=GBP&to=USD,EUR"


@dataclass(frozen=True)
class ProductionFeed:
    """Maps ladder fields to dotted JSON paths after HTTP GET."""

    feed_id: str
    url: str
    field_paths: dict[str, tuple[str, ...]]
    description: str = ""


PRODUCTION_FEEDS: dict[str, ProductionFeed] = {
    "fx_gbp_cross": ProductionFeed(
        feed_id="fx_gbp_cross",
        url=_DEFAULT_FX_URL,
        field_paths={
            "fare_price": ("rates", "USD"),
            "seat_count": ("amount",),
            "route_code": ("base",),
        },
        description="GBP cross-rate feed (Frankfurter public API)",
    ),
}


def _dig(data: Any, path: tuple[str, ...]) -> Any:
    cur = data
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def fetch_production_context(
    feed_id: str,
    *,
    url_override: str | None = None,
    timeout: float = 15.0,
) -> dict[str, Any]:
    """
    Fetch a registered production feed and map JSON into alt-data ctx keys.

    Override URL via ``url_override`` or env ``ALTDATA_PRODUCTION_URL``.
    """
    feed = PRODUCTION_FEEDS.get(feed_id)
    if feed is None:
        raise ValueError(f"unknown production feed: {feed_id}")
    url = url_override or os.getenv("ALTDATA_PRODUCTION_URL") or feed.url
    resp = httpx.get(url, timeout=timeout, follow_redirects=True)
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, dict):
        raise ValueError("production feed must return a JSON object")

    ctx: dict[str, Any] = {
        "source_url": url,
        "production_feed_id": feed_id,
        "raw_json": data,
    }
    for field, path in feed.field_paths.items():
        val = _dig(data, path)
        if val is not None:
            ctx[field] = val
            ctx[f"demo_{field}"] = val
    return ctx


def list_production_feeds() -> list[dict[str, str]]:
    return [
        {
            "feed_id": f.feed_id,
            "url": f.url,
            "description": f.description,
        }
        for f in PRODUCTION_FEEDS.values()
    ]
