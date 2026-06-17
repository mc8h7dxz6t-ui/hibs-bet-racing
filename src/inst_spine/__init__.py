"""Inst++ spine — domain-agnostic audit, gates, and rate math."""

from inst_spine.check import run_institutional_check
from inst_spine.clocks import LamportClock, VectorClock, monotonic_seconds
from inst_spine.contracts import ApiIntent, LedgerEntry, RunManifest
from inst_spine.gates.circuit import CircuitBreaker, CircuitState
from inst_spine.gates.engine import GateEngine, GateResult
from inst_spine.hash import chain_hash, verify_chain
from inst_spine.ledger import AppendOnlyLedger
from inst_spine.rates import TokenBucket, ZScoreDriftDetector

__all__ = [
    "ApiIntent",
    "AppendOnlyLedger",
    "CircuitBreaker",
    "CircuitState",
    "GateEngine",
    "GateResult",
    "LamportClock",
    "LedgerEntry",
    "RunManifest",
    "TokenBucket",
    "VectorClock",
    "ZScoreDriftDetector",
    "chain_hash",
    "monotonic_seconds",
    "run_institutional_check",
    "verify_chain",
]

__version__ = "0.1.0"
