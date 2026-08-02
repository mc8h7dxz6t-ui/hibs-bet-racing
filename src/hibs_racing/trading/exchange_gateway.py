"""Live exchange write surface — armed when operator flags allow capital."""

from __future__ import annotations

import logging
import os
from typing import Any

from hibs_racing.trading.config import live_trading_enabled

logger = logging.getLogger(__name__)


class LiveExchangeWriteDisabled(RuntimeError):
    """Raised when live trading flag blocks capital packets."""


def _execution_live_armed() -> bool:
    return (os.environ.get("HIBS_EXECUTION_LIVE") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def dispatch_live_order(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Exchange REST write endpoint for live money packets.

    Requires HIBS_LIVE_TRADING_ENABLED=true and HIBS_EXECUTION_LIVE=1 (operator arm).
    """
    if not live_trading_enabled():
        raise LiveExchangeWriteDisabled(
            "HIBS_LIVE_TRADING_ENABLED=false — live exchange write stubbed (zero capital risk)"
        )
    if not _execution_live_armed():
        raise LiveExchangeWriteDisabled(
            "HIBS_EXECUTION_LIVE unset — operator must arm micro fund before exchange writes"
        )

    from hibs_racing.odds.matchbook import MatchbookClient

    client = MatchbookClient()
    try:
        return client.place_back_offer(
            market_id=int(payload["market_id"]),
            runner_id=int(payload["runner_id"]),
            odds=float(payload["odds"]),
            stake=float(payload["stake"]),
        )
    finally:
        client.close()
