"""Cross-platform product bar URL helpers for racing."""

from __future__ import annotations

from hibs_racing.product_links import (
    football_home_url,
    line_trader_url,
    product_bar_context,
    racing_cards_url,
    trading_status_url,
)


def test_racing_cards_url_local(monkeypatch):
    monkeypatch.delenv("HIBS_RACING_PUBLIC_URL", raising=False)
    monkeypatch.delenv("HIBS_RACING_BASE_URL", raising=False)
    assert racing_cards_url() == "/cards"


def test_cross_app_urls_with_football_base(monkeypatch):
    monkeypatch.setenv("HIBS_FOOTBALL_BASE_URL", "https://hibs-bet.co.uk")
    assert football_home_url() == "https://hibs-bet.co.uk/"
    assert trading_status_url() == "https://hibs-bet.co.uk/harvested-execution"
    assert line_trader_url() == "https://hibs-bet.co.uk/line-trader"


def test_product_bar_context_active_racing(monkeypatch):
    monkeypatch.setenv("HIBS_FOOTBALL_BASE_URL", "https://hibs-bet.co.uk")
    ctx = product_bar_context(active="racing")
    assert ctx["hibs_product_active"] == "racing"
    assert "hibs-bet.co.uk" in ctx["hibs_trading_status_url"]
