"""Cross-product navigation URLs — mirrors hibs-bet product_links."""

from __future__ import annotations

import os
from typing import Any, Dict


def _football_base() -> str:
    return (os.getenv("HIBS_FOOTBALL_BASE_URL") or os.getenv("HIBS_PRODUCTION_URL") or "").strip().rstrip("/")


def football_home_url() -> str:
    base = _football_base()
    return f"{base}/" if base else "/"


def racing_cards_url() -> str:
    public = (os.getenv("HIBS_RACING_PUBLIC_URL") or "").strip().rstrip("/")
    if public:
        return f"{public}/cards" if not public.endswith("/cards") else public
    prefix = (os.getenv("HIBS_RACING_BASE_URL") or "").strip().rstrip("/")
    if prefix:
        return f"{prefix}/cards" if not prefix.endswith("/cards") else prefix
    return "/cards"


def trading_status_url() -> str:
    explicit = (os.getenv("HIBS_TRADING_STATUS_URL") or "").strip().rstrip("/")
    if explicit:
        return explicit
    base = _football_base()
    if base:
        return f"{base}/harvested-execution"
    return "/harvested-execution"


def line_trader_url() -> str:
    explicit = (os.getenv("HIBS_LINE_TRADER_URL") or "").strip().rstrip("/")
    if explicit:
        return explicit
    base = _football_base()
    if base:
        return f"{base}/line-trader"
    return "/line-trader"


def product_bar_context(*, active: str | None = None) -> Dict[str, Any]:
    active_product = (active or os.getenv("HIBS_PRODUCT_ACTIVE") or "racing").strip().lower()
    cards = racing_cards_url()
    return {
        "hibs_football_home_url": football_home_url(),
        "hibs_football_base_url": _football_base() or "/",
        "hibs_racing_home_url": cards,
        "hibs_racing_cards_url": cards,
        "hibs_racing_base_url": (os.getenv("HIBS_RACING_PUBLIC_URL") or os.getenv("HIBS_RACING_BASE_URL") or "").rstrip("/"),
        "hibs_trading_status_url": trading_status_url(),
        "hibs_line_trader_url": line_trader_url(),
        "hibs_product_active": active_product,
    }
