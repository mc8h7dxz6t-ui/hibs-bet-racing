"""Live exchange write surface — stubbed when HIBS_LIVE_TRADING_ENABLED=false."""

from __future__ import annotations

import logging
from typing import Any

from hibs_racing.trading.config import live_trading_enabled

logger = logging.getLogger(__name__)


class LiveExchangeWriteDisabled(RuntimeError):
    """Raised when live trading flag blocks capital packets."""


def dispatch_live_order(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Exchange REST/WebSocket write endpoint for live money packets.

    SANDBOXED: when HIBS_LIVE_TRADING_ENABLED is false this function never
    contacts the exchange — callers must route to simulated_trades instead.
    """
    if not live_trading_enabled():
        raise LiveExchangeWriteDisabled(
            "HIBS_LIVE_TRADING_ENABLED=false — live exchange write stubbed (zero capital risk)"
        )

    # -------------------------------------------------------------------------
    # LIVE CAPITAL PATH INTENTIONALLY DISABLED IN THIS RELEASE.
    # Uncomment and wire MatchbookClient.place_back_offer only after governance
    # sign-off. Until then, even with HIBS_LIVE_TRADING_ENABLED=true we fail closed.
    # -------------------------------------------------------------------------
    # from hibs_racing.odds.matchbook import MatchbookClient
    # client = MatchbookClient()
    # try:
    #     return client.place_back_offer(
    #         market_id=int(payload["market_id"]),
    #         runner_id=int(payload["runner_id"]),
    #         odds=float(payload["odds"]),
    #         stake=float(payload["stake"]),
    #     )
    # finally:
    #     client.close()

    logger.error("live trading flag set but exchange write path remains commented out")
    raise LiveExchangeWriteDisabled("live exchange write path not armed in this build")
