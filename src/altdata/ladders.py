"""Field ladder registry — domain-agnostic."""

from __future__ import annotations

from typing import Any, Callable, Dict, List

# Example feed: airline fare basket (laser-focused demo target)
FIELD_LADDERS: Dict[str, List[str]] = {
    "fare_price": ["primary_api", "mirror_api", "html_scrape", "structural_rescue"],
    "seat_count": ["primary_api", "html_scrape", "structural_rescue"],
    "route_code": ["primary_api", "mirror_api"],
}

Fetcher = Callable[[str, dict[str, Any]], Any]


def default_fetchers() -> dict[str, Fetcher]:
    """Stub fetchers for testing — replace per feed deployment."""

    def _primary_api(field: str, ctx: dict[str, Any]) -> Any:
        if field == "fare_price":
            return ctx.get("demo_price")
        if field == "seat_count":
            return ctx.get("demo_seats")
        if field == "route_code":
            return ctx.get("demo_route")
        return None

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
