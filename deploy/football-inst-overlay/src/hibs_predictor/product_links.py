"""Cross-product navigation URLs (football · racing · trading · FVE line trader)."""

from __future__ import annotations

import os
from typing import Any, Dict


def _env_truthy(name: str) -> bool:
    return (os.getenv(name) or "").strip().lower() in ("1", "true", "yes", "on")


def football_home_url() -> str:
    raw = (os.getenv("HIBS_FOOTBALL_HOME_URL") or "/").strip()
    return raw or "/"


def racing_base_url() -> str:
    explicit = (os.getenv("HIBS_RACING_BASE_URL") or "").strip().rstrip("/")
    if explicit:
        return explicit
    return "/racing"


def racing_cards_url() -> str:
    base = racing_base_url()
    if base.startswith("/"):
        return f"{base}/cards" if not base.endswith("/cards") else base
    return f"{base}/cards"


def trading_status_url() -> str:
    explicit = (os.getenv("HIBS_TRADING_STATUS_URL") or "").strip().rstrip("/")
    if explicit:
        return explicit
    base = (os.getenv("HIBS_PRODUCTION_URL") or os.getenv("HIBS_FOOTBALL_BASE_URL") or "").strip().rstrip("/")
    if base:
        return f"{base}/harvested-execution"
    return "/harvested-execution"


def line_trader_url() -> str:
    explicit = (os.getenv("HIBS_LINE_TRADER_URL") or "").strip().rstrip("/")
    if explicit:
        return explicit
    from hibs_predictor.fve_status import line_trader_page_url as _page

    return _page()


def line_trader_url_absolute() -> str:
    explicit = (os.getenv("HIBS_LINE_TRADER_URL") or "").strip().rstrip("/")
    if explicit:
        return explicit
    base = (os.getenv("HIBS_PRODUCTION_URL") or "").strip().rstrip("/")
    if base:
        return f"{base}/line-trader"
    return line_trader_url()


def fve_docs_url() -> str:
    explicit = (os.getenv("HIBS_FVE_DOCS_URL") or "").strip()
    if explicit:
        return explicit
    base = (os.getenv("FVE_API_URL") or "http://127.0.0.1:8010").rstrip("/")
    return f"{base}/docs"


def infer_product_active(path: str) -> str:
    p = (path or "").strip().lower().rstrip("/") or "/"
    if p.startswith("/harvested-execution"):
        return "trading"
    if p.startswith("/line-trader"):
        return "lines"
    return "football"


def infer_football_nav_active(path: str) -> str:
    p = (path or "").strip().lower().rstrip("/") or "/"
    routes = {
        "/": "dashboard",
        "/acca": "acca",
        "/insights": "insights",
        "/performance": "performance",
        "/tables": "tables",
        "/players": "players",
        "/status": "status",
        "/guide": "guide",
        "/settings": "settings",
        "/tracker": "tracker",
    }
    return routes.get(p, "")


def product_bar_context(*, active: str | None = None) -> Dict[str, Any]:
    active_product = (active or os.getenv("HIBS_PRODUCT_ACTIVE") or "football").strip().lower()
    if active_product not in ("football", "racing", "trading", "lines", "fve"):
        active_product = "football"
    racing = racing_base_url()
    return {
        "hibs_football_home_url": football_home_url(),
        "hibs_racing_base_url": racing,
        "hibs_racing_cards_url": racing_cards_url(),
        "hibs_trading_status_url": trading_status_url(),
        "hibs_line_trader_url": line_trader_url(),
        "hibs_fve_docs_url": fve_docs_url(),
        "hibs_product_active": active_product,
        "portfolio_api_url": (os.getenv("HIBS_PORTFOLIO_API_URL") or "/api/racing/portfolio/summary"),
        "portfolio_racing_url": f"{racing}/portfolio" if not racing.endswith("/portfolio") else racing,
        "portfolio_football_url": "/tracker",
        "trading_metrics_url": (os.getenv("TRADING_METRICS_URL") or "http://127.0.0.1:9109").rstrip("/"),
        "hibs_fve_integration": _env_truthy("HIBS_FVE_INTEGRATION"),
    }
