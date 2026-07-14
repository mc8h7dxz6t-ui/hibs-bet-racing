"""HTTP + stub fetchers for alt-data field ladders."""

from __future__ import annotations

import json
from typing import Any, Callable

import httpx

FIELD_LADDERS: dict[str, list[str]] = {
    "fare_price": ["primary_api", "mirror_api", "html_scrape", "structural_rescue"],
    "seat_count": ["primary_api", "html_scrape", "structural_rescue"],
    "route_code": ["primary_api", "mirror_api"],
}

Fetcher = Callable[[str, dict[str, Any]], Any]


def fetch_url_context(url: str, *, timeout: float = 10.0) -> dict[str, Any]:
    """Fetch URL — JSON body merged into ctx; HTML stored as raw_html for rescue."""
    resp = httpx.get(url, timeout=timeout, follow_redirects=True)
    resp.raise_for_status()
    ctx: dict[str, Any] = {"raw_html": resp.text, "source_url": url}
    content_type = (resp.headers.get("content-type") or "").lower()
    if "json" in content_type or resp.text.strip().startswith(("{", "[")):
        try:
            data = resp.json()
            if isinstance(data, dict):
                ctx.update(data)
        except json.JSONDecodeError:
            pass
    return ctx


def http_fetchers() -> dict[str, Fetcher]:
    """Fetchers that read from ctx populated by fetch_url_context."""

    def _http_json(field: str, ctx: dict[str, Any]) -> Any:
        return ctx.get(field) or ctx.get(f"demo_{field}")

    def _html_scrape(field: str, ctx: dict[str, Any]) -> Any:
        return ctx.get(f"scrape_{field}")

    def _structural_rescue(field: str, ctx: dict[str, Any]) -> Any:
        from altdata.structural_rescue import structural_rescue

        html = ctx.get("raw_html") or ""
        return structural_rescue(html, field)

    return {
        "primary_api": _http_json,
        "mirror_api": _http_json,
        "html_scrape": _html_scrape,
        "structural_rescue": _structural_rescue,
    }


def default_fetchers() -> dict[str, Fetcher]:
    """In-process stub fetchers for offline demo."""

    def _primary_api(field: str, ctx: dict[str, Any]) -> Any:
        if field == "fare_price":
            return ctx.get("demo_price") or ctx.get("fare_price")
        if field == "seat_count":
            return ctx.get("demo_seats") or ctx.get("seat_count")
        if field == "route_code":
            return ctx.get("demo_route") or ctx.get("route_code")
        return ctx.get(field)

    def _mirror_api(field: str, ctx: dict[str, Any]) -> Any:
        return ctx.get(f"mirror_{field}")

    def _html_scrape(field: str, ctx: dict[str, Any]) -> Any:
        return ctx.get(f"scrape_{field}")

    def _structural_rescue(field: str, ctx: dict[str, Any]) -> Any:
        from altdata.structural_rescue import structural_rescue

        html = ctx.get("raw_html") or ""
        return structural_rescue(html, field)

    return {
        "primary_api": _primary_api,
        "mirror_api": _mirror_api,
        "html_scrape": _html_scrape,
        "structural_rescue": _structural_rescue,
    }
