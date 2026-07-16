"""Outbound broker negotiation — blocked unless explicitly armed."""

from __future__ import annotations

from hibs_racing.trading.config import liquidity_router_active


class OutboundBrokerBlocked(RuntimeError):
    """Raised when router would contact external venue APIs."""


def negotiate_secondary_venue(*, channel: str, payload: dict) -> dict:
    """
    Secondary venue / MGA negotiation surface.

    SANDBOXED: when HIBS_LIQUIDITY_ROUTER_ACTIVE is false, never opens outbound connections.
    """
    if not liquidity_router_active():
        raise OutboundBrokerBlocked(
            "HIBS_LIQUIDITY_ROUTER_ACTIVE=false — outbound broker negotiation stubbed"
        )
    raise OutboundBrokerBlocked(
        "outbound broker path not armed in this build (simulation ledger only)"
    )
