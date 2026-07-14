"""Cross-product navigation URLs (football · racing · trading · FVE line trader)."""

from __future__ import annotations

import os
from typing import Any


def _site_domain() -> str:
    return (os.getenv("HIBS_DOMAIN") or "hibs-bet.co.uk").strip()


def _url_prefix() -> str:
    return (os.getenv("HIBS_URL_PREFIX") or "").strip().rstrip("/")


def _football_base() -> str:
    return (
        os.getenv("HIBS_FOOTBALL_BASE_URL") or os.getenv("HIBS_PRODUCTION_URL") or ""
    ).strip().rstrip("/")


def football_home_url() -> str:
    explicit = (os.getenv("HIBS_FOOTBALL_HOME_URL") or "").strip().rstrip("/")
    if explicit:
        return explicit + "/"
    base = _football_base()
    if base:
        return f"{base}/"
    return f"https://{_site_domain()}/"


def racing_base_url() -> str:
    public = (os.getenv("HIBS_RACING_PUBLIC_URL") or "").strip().rstrip("/")
    if public:
        return public
    explicit = (os.getenv("HIBS_RACING_BASE_URL") or "").strip().rstrip("/")
    if explicit:
        return explicit
    prefix = _url_prefix()
    if prefix:
        return prefix
    return "/racing"


def racing_cards_url() -> str:
    public = (os.getenv("HIBS_RACING_PUBLIC_URL") or "").strip().rstrip("/")
    if public:
        return f"{public}/cards" if not public.endswith("/cards") else public
    prefix = _url_prefix()
    if prefix:
        return f"{prefix}/cards"
    explicit = (os.getenv("HIBS_RACING_BASE_URL") or "").strip().rstrip("/")
    if explicit:
        return f"{explicit}/cards" if not explicit.endswith("/cards") else explicit
    return "/cards"


def trading_status_url() -> str:
    explicit = (os.getenv("HIBS_TRADING_STATUS_URL") or "").strip().rstrip("/")
    if explicit:
        return explicit
    base = _football_base()
    if base:
        return f"{base}/harvested-execution"
    return f"https://{_site_domain()}/harvested-execution"


def line_trader_url() -> str:
    explicit = (os.getenv("HIBS_LINE_TRADER_URL") or "").strip().rstrip("/")
    if explicit:
        return explicit
    base = _football_base()
    if base:
        return f"{base}/line-trader"
    return f"https://{_site_domain()}/line-trader"


def portfolio_api_url() -> str:
    explicit = (os.getenv("HIBS_PORTFOLIO_API_URL") or "").strip()
    if explicit:
        return explicit
    if _url_prefix():
        return "/api/racing/portfolio/summary"
    return "/api/portfolio/summary"


def product_bar_context(*, active: str | None = None) -> dict[str, Any]:
    active_product = (active or os.getenv("HIBS_PRODUCT_ACTIVE") or "racing").strip().lower()
    if active_product not in ("football", "racing", "trading", "lines", "fve"):
        active_product = "racing"
    racing = racing_base_url()
    return {
        "hibs_football_home_url": football_home_url(),
        "hibs_football_base_url": _football_base() or "http://127.0.0.1:5000",
        "hibs_racing_base_url": racing,
        "hibs_racing_home_url": racing_cards_url(),
        "hibs_racing_cards_url": racing_cards_url(),
        "hibs_trading_status_url": trading_status_url(),
        "hibs_line_trader_url": line_trader_url(),
        "hibs_product_active": active_product,
        "portfolio_api_url": portfolio_api_url(),
    }
