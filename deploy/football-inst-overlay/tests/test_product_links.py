"""Cross-platform product bar URL helpers."""

from __future__ import annotations

from hibs_predictor.product_links import (
    infer_football_nav_active,
    infer_product_active,
    product_bar_context,
    racing_cards_url,
    trading_status_url,
)


def test_infer_product_active():
    assert infer_product_active("/") == "football"
    assert infer_product_active("/insights") == "football"
    assert infer_product_active("/harvested-execution") == "trading"
    assert infer_product_active("/line-trader") == "lines"


def test_infer_football_nav_active():
    assert infer_football_nav_active("/") == "dashboard"
    assert infer_football_nav_active("/acca") == "acca"
    assert infer_football_nav_active("/harvested-execution") == ""


def test_product_bar_context_defaults(monkeypatch):
    monkeypatch.delenv("HIBS_RACING_BASE_URL", raising=False)
    ctx = product_bar_context()
    assert ctx["hibs_product_active"] == "football"
    assert ctx["hibs_racing_cards_url"] == "/racing/cards"
    assert ctx["hibs_trading_status_url"] == "/harvested-execution"


def test_product_bar_context_env_overrides(monkeypatch):
    monkeypatch.setenv("HIBS_RACING_BASE_URL", "https://hibs-bet.co.uk/racing")
    monkeypatch.setenv("HIBS_TRADING_STATUS_URL", "/harvested-execution")
    assert racing_cards_url() == "https://hibs-bet.co.uk/racing/cards"
    assert trading_status_url() == "/harvested-execution"
    ctx = product_bar_context(active="trading")
    assert ctx["hibs_product_active"] == "trading"
