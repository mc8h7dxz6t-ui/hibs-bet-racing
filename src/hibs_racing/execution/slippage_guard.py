"""Execution slippage guard — SERIALIZABLE-grade EV protection for Matchbook fills."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional


class ExecutionState(str, Enum):
    SUBMITTED = "SUBMITTED"
    FILLED = "FILLED"
    HELD = "HELD"  # slippage breach — auditable, no capital at risk
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class SlippageVerdict:
    allowed: bool
    state: ExecutionState
    slippage_pct: float
    ev_burn_pct: float
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "allowed": self.allowed,
            "state": self.state.value,
            "slippage_pct": round(self.slippage_pct, 4),
            "ev_burn_pct": round(self.ev_burn_pct, 4),
            "reason": self.reason,
        }


def compute_slippage_pct(requested_odds: float, filled_odds: float) -> float:
    if requested_odds <= 1 or filled_odds <= 1:
        return 100.0
    # Lower filled odds vs requested = worse for backer
    return max(0.0, ((requested_odds - filled_odds) / requested_odds) * 100.0)


def compute_ev_burn_pct(model_prob: float, requested_odds: float, filled_odds: float) -> float:
    """Fraction of model EV destroyed by fill slippage."""
    if model_prob <= 0 or requested_odds <= 1 or filled_odds <= 1:
        return 100.0
    ev_req = model_prob * requested_odds - 1.0
    ev_fill = model_prob * filled_odds - 1.0
    if ev_req <= 0:
        return 0.0
    burn = max(0.0, (ev_req - ev_fill) / ev_req)
    return burn * 100.0


def evaluate_fill_slippage(
    *,
    requested_odds: float,
    filled_odds: float,
    model_prob: float,
    max_ev_burn_pct: float = 1.5,
) -> SlippageVerdict:
    """
    Fail-closed execution gate. If EV burn > 1.5%, move to HELD (hash-chain auditable).
    """
    slip = compute_slippage_pct(requested_odds, filled_odds)
    burn = compute_ev_burn_pct(model_prob, requested_odds, filled_odds)
    if burn > max_ev_burn_pct:
        return SlippageVerdict(
            allowed=False,
            state=ExecutionState.HELD,
            slippage_pct=slip,
            ev_burn_pct=burn,
            reason=f"EV burn {burn:.2f}% > {max_ev_burn_pct}% — HELD for audit",
        )
    return SlippageVerdict(
        allowed=True,
        state=ExecutionState.FILLED,
        slippage_pct=slip,
        ev_burn_pct=burn,
        reason="within slippage budget",
    )


def serializable_order_guard(
    conn: Any,
    *,
    order_id: str,
    requested_odds: float,
    filled_odds: float,
    model_prob: float,
) -> SlippageVerdict:
    """
    PostgreSQL SERIALIZABLE transaction wrapper (caller supplies psycopg connection).

    Sets isolation level, updates order row, blocks on HELD when slippage breaches.
    """
    verdict = evaluate_fill_slippage(
        requested_odds=requested_odds,
        filled_odds=filled_odds,
        model_prob=model_prob,
    )
    try:
        conn.isolation_level = None
        with conn.cursor() as cur:
            cur.execute("BEGIN ISOLATION LEVEL SERIALIZABLE")
            cur.execute(
                """
                UPDATE execution_orders
                SET state = %s, filled_odds = %s, slippage_pct = %s, ev_burn_pct = %s, held_reason = %s
                WHERE order_id = %s
                """,
                (
                    verdict.state.value,
                    filled_odds,
                    verdict.slippage_pct,
                    verdict.ev_burn_pct,
                    None if verdict.allowed else verdict.reason,
                    order_id,
                ),
            )
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    return verdict
