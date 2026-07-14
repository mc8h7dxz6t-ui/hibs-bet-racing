"""Inst++ spine — domain-agnostic audit, gates, and rate math."""

from inst_spine.check import run_institutional_check
from inst_spine.clocks import LamportClock, VectorClock, monotonic_seconds
from inst_spine.contracts import ApiIntent, LedgerEntry, RunManifest
from inst_spine.gates.circuit import CircuitBreaker, CircuitState
from inst_spine.gates.engine import GateEngine, GateResult
from inst_spine.hash import chain_hash, verify_chain
from inst_spine.ledger import AppendOnlyLedger
from inst_spine.rates import (
    IdempotencyBackend,
    MemoryIdempotencyBackend,
    RedisIdempotencyBackend,
    TokenBucket,
    ZScoreConfig,
    ZScoreDriftDetector,
    idempotency_backend_from_env,
    token_bucket_backend_from_env,
)
from inst_spine.wal import WALWriter

__all__ = [
    "ApiIntent",
    "AppendOnlyLedger",
    "CircuitBreaker",
    "CircuitState",
    "GateEngine",
    "GateResult",
    "IdempotencyBackend",
    "LamportClock",
    "LedgerEntry",
    "MemoryIdempotencyBackend",
    "RedisIdempotencyBackend",
    "RunManifest",
    "TokenBucket",
    "WALWriter",
    "ZScoreConfig",
    "VectorClock",
    "ZScoreDriftDetector",
    "chain_hash",
    "idempotency_backend_from_env",
    "monotonic_seconds",
    "run_institutional_check",
    "token_bucket_backend_from_env",
    "verify_chain",
]

__version__ = "0.1.0"
