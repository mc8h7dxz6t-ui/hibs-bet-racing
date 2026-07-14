"""Tests for REST market fallback helpers."""

from __future__ import annotations

from hibs_predictor.trading_core.rest_market_fallback import (
    build_rest_fallback_config,
    normalize_coinbase_rest_trade,
    rest_market_fallback_enabled,
)


def test_normalize_coinbase_rest_trade():
    pkt = normalize_coinbase_rest_trade(
        "BTC-USD",
        {"price": "50000", "size": "0.01", "trade_id": 99, "time": "t", "side": "buy"},
    )
    assert pkt is not None
    assert pkt["S"] in ("BTCUSD", "BTC/USD")
    assert pkt["p"] == 50000.0


def test_build_rest_fallback_config_disabled(monkeypatch):
    monkeypatch.delenv("TRADING_REST_MARKET_FALLBACK", raising=False)
    monkeypatch.delenv("TRADING_PREFER_REST_MARKET_DATA", raising=False)
    assert build_rest_fallback_config(equity_symbols=("AAPL",), crypto_symbols=()) is None


def test_build_rest_fallback_config_enabled(monkeypatch):
    monkeypatch.setenv("TRADING_REST_MARKET_FALLBACK", "1")
    cfg = build_rest_fallback_config(equity_symbols=("AAPL",), crypto_symbols=("BTCUSD",))
    assert cfg is not None
    assert cfg.equity_symbols == ("AAPL",)
    assert rest_market_fallback_enabled() is True
