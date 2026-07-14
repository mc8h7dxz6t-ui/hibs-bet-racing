"""Cross-platform product bar URL helpers."""

from __future__ import annotations

from hibs_racing.product_links import (
    football_home_url,
    line_trader_url,
    portfolio_api_url,
    product_bar_context,
    racing_cards_url,
    trading_status_url,
)


def test_football_home_defaults_to_production_domain(monkeypatch):
    monkeypatch.delenv("HIBS_FOOTBALL_HOME_URL", raising=False)
    monkeypatch.setenv("HIBS_DOMAIN", "hibs-bet.co.uk")
    assert football_home_url() == "https://hibs-bet.co.uk/"


def test_racing_cards_local_direct_port(monkeypatch):
    monkeypatch.delenv("HIBS_RACING_PUBLIC_URL", raising=False)
    monkeypatch.delenv("HIBS_RACING_BASE_URL", raising=False)
    monkeypatch.delenv("HIBS_URL_PREFIX", raising=False)
    assert racing_cards_url() == "/cards"


def test_racing_cards_subpath(monkeypatch):
    monkeypatch.delenv("HIBS_RACING_PUBLIC_URL", raising=False)
    monkeypatch.setenv("HIBS_URL_PREFIX", "/racing")
    assert racing_cards_url() == "/racing/cards"


def test_racing_cards_public_url(monkeypatch):
    monkeypatch.setenv("HIBS_RACING_PUBLIC_URL", "https://hibs-bet.co.uk/racing")
    assert racing_cards_url() == "https://hibs-bet.co.uk/racing/cards"


def test_portfolio_api_url_subpath(monkeypatch):
    monkeypatch.delenv("HIBS_PORTFOLIO_API_URL", raising=False)
    monkeypatch.setenv("HIBS_URL_PREFIX", "/racing")
    assert portfolio_api_url() == "/api/racing/portfolio/summary"


def test_portfolio_api_url_local(monkeypatch):
    monkeypatch.delenv("HIBS_PORTFOLIO_API_URL", raising=False)
    monkeypatch.delenv("HIBS_URL_PREFIX", raising=False)
    assert portfolio_api_url() == "/api/portfolio/summary"


def test_trading_and_lines_urls(monkeypatch):
    monkeypatch.delenv("HIBS_TRADING_STATUS_URL", raising=False)
    monkeypatch.delenv("HIBS_LINE_TRADER_URL", raising=False)
    monkeypatch.setenv("HIBS_DOMAIN", "hibs-bet.co.uk")
    assert trading_status_url() == "https://hibs-bet.co.uk/harvested-execution"
    assert line_trader_url() == "https://hibs-bet.co.uk/line-trader"


def test_product_bar_context_active_racing(monkeypatch):
    monkeypatch.delenv("HIBS_RACING_PUBLIC_URL", raising=False)
    monkeypatch.delenv("HIBS_URL_PREFIX", raising=False)
    ctx = product_bar_context(active="racing")
    assert ctx["hibs_product_active"] == "racing"
    assert ctx["hibs_racing_cards_url"] == "/cards"
    assert ctx["portfolio_api_url"] == "/api/portfolio/summary"
