"""Event-driven execution trading engine (feature-flagged, sandboxed by default)."""

from hibs_racing.trading.config import live_trading_enabled

__all__ = ["live_trading_enabled"]
