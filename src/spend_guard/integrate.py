"""Integration hook for Proxy-Risk / LiteLLM-style gateways."""

from __future__ import annotations

from pathlib import Path

from spend_guard.gateway import SpendGuardGateway, SpendRequest
from spend_guard.wallet import SpendWallet


def reserve_api_call(
    *,
    request_id: str,
    estimated_cost: float,
    wallet_db: Path,
    ledger_db: Path | None = None,
    service: str = "llm-api",
) -> dict:
    """
  Drop-in before upstream HTTP dispatch:
    result = reserve_api_call(...)
    if result['decision'] != 'approve': return 409
    # ... call upstream ...
    settle_api_call(hold_id=result['hold_id'], ...)
    """
    wallet = SpendWallet(wallet_db)
    from inst_spine.ledger import AppendOnlyLedger

    ledger = AppendOnlyLedger(ledger_db) if ledger_db else None
    gw = SpendGuardGateway(wallet=wallet, ledger=ledger)
    resp = gw.reserve(SpendRequest(request_id=request_id, estimated_cost=estimated_cost, service=service))
    return resp.to_dict()


def settle_api_call(
    *,
    hold_id: str,
    actual_cost: float,
    request_id: str,
    wallet_db: Path,
    ledger_db: Path | None = None,
    service: str = "llm-api",
) -> dict:
    wallet = SpendWallet(wallet_db)
    from inst_spine.ledger import AppendOnlyLedger

    ledger = AppendOnlyLedger(ledger_db) if ledger_db else None
    gw = SpendGuardGateway(wallet=wallet, ledger=ledger)
    resp = gw.settle(hold_id, actual_cost=actual_cost, request_id=request_id, service=service)
    return resp.to_dict()
