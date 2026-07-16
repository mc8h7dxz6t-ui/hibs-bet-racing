"""Trading engine environment configuration."""

from __future__ import annotations

import os


def _env_flag(name: str, *, default: bool = False) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    return int(raw)


def _env_float(name: str, default: float) -> float:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    return float(raw)


def live_trading_enabled() -> bool:
    """When false, orders are simulated only — no live exchange writes."""
    return _env_flag("HIBS_LIVE_TRADING_ENABLED", default=False)


def execution_latency_max_ms() -> int:
    return _env_int("HIBS_EXECUTION_LATENCY_MAX_MS", 250)


def slippage_max_ticks() -> float:
    return _env_float("HIBS_SLIPPAGE_MAX_TICKS", 2.0)


def idempotency_window_ms() -> int:
    return _env_int("HIBS_TRADING_IDEMPOTENCY_MS", 5000)


def stream_ws_url() -> str:
    return (os.environ.get("HIBS_MATCHBOOK_STREAM_WS_URL") or "").strip()


def stream_tick_size() -> float:
    return _env_float("HIBS_TRADING_ODDS_TICK_SIZE", 0.01)


def initial_wallet_balance() -> float:
    return _env_float("HIBS_TRADING_WALLET_BALANCE", 1000.0)
