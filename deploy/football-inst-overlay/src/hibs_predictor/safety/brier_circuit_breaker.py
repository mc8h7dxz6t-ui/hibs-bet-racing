"""Runtime Brier calibration circuit breaker — OPEN / HALF_OPEN / CLOSED + hash chain."""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, Optional


class BreakerState(str, Enum):
    CLOSED = "CLOSED"  # normal execution
    OPEN = "OPEN"  # execution lockout — diagnostic only
    HALF_OPEN = "HALF_OPEN"  # probe window after cooldown


@dataclass
class BrierCircuitBreaker:
    """
    Finite state machine for calibration drift.

    Threshold default 0.25 (R8 place / institutional lockout). Football F10 uses 0.22
    via `threshold` override in hourly runner.
    """

    threshold: float = 0.25
    min_samples: int = 20
    cooldown_sec: float = 3600.0
    half_open_samples: int = 5
    state: BreakerState = BreakerState.CLOSED
    reason: str = ""
    last_brier: Optional[float] = None
    last_n: int = 0
    _opened_at: Optional[float] = None
    _half_open_passes: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def evaluate(self, brier: float, n: int, *, now: Optional[float] = None) -> BreakerState:
        import time

        ts = now if now is not None else time.time()
        with self._lock:
            self.last_brier = float(brier)
            self.last_n = int(n)
            insufficient = n < self.min_samples

            if self.state == BreakerState.OPEN:
                if self._opened_at is not None and (ts - self._opened_at) >= self.cooldown_sec:
                    self.state = BreakerState.HALF_OPEN
                    self._half_open_passes = 0
                    self.reason = "cooldown elapsed — probe HALF_OPEN"
                return self.state

            if self.state == BreakerState.HALF_OPEN:
                if insufficient or brier > self.threshold:
                    self._trip_open(f"brier {brier:.4f} > {self.threshold} in HALF_OPEN", ts)
                    return self.state
                self._half_open_passes += 1
                if self._half_open_passes >= self.half_open_samples:
                    self.state = BreakerState.CLOSED
                    self.reason = "calibration normalized"
                    self._opened_at = None
                return self.state

            # CLOSED
            if not insufficient and brier > self.threshold:
                self._trip_open(f"brier {brier:.4f} > {self.threshold} (n={n})", ts)
            return self.state

    def _trip_open(self, reason: str, ts: float) -> None:
        self.state = BreakerState.OPEN
        self.reason = reason
        self._opened_at = ts
        self._half_open_passes = 0

    def allows_execution(self) -> tuple[bool, str]:
        with self._lock:
            if self.state == BreakerState.OPEN:
                return False, f"OPEN: {self.reason}"
            if self.state == BreakerState.HALF_OPEN:
                return False, f"HALF_OPEN probe: {self.reason}"
            return True, "CLOSED"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "state": self.state.value,
            "reason": self.reason,
            "last_brier": self.last_brier,
            "last_n": self.last_n,
            "threshold": self.threshold,
            "min_samples": self.min_samples,
        }


def _append_hash_chain(event: Dict[str, Any], *, ledger_path: Path) -> Dict[str, Any]:
    """Append Brier observation to Inst++ ledger when available; else JSONL fallback."""
    try:
        from inst_spine.ledger import AppendOnlyLedger

        db = ledger_path if ledger_path.suffix == ".sqlite" else ledger_path.with_suffix(".sqlite")
        ledger = AppendOnlyLedger(db, writer_id="brier-circuit")
        entry = ledger.append(event_type="brier_circuit_breaker", payload=event)
        return {"entry_hash": entry.entry_hash, "lamport_seq": entry.lamport_seq}
    except Exception:
        fallback = ledger_path.parent / "brier_circuit.jsonl"
        fallback.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(event, default=str) + "\n"
        with fallback.open("a", encoding="utf-8") as fh:
            fh.write(line)
        return event


def execution_lockout_active() -> bool:
    """True when hourly Brier circuit breaker has tripped execution lockout."""
    flag = (os.getenv("HIBS_EXECUTION_LOCKOUT") or "").strip().lower()
    if flag in ("1", "true", "yes", "on"):
        return True
    state_path = Path(
        os.getenv("HIBS_BRIER_STATE_PATH", "/opt/hibs-bet/data/brier_circuit_state.json")
    )
    if state_path.is_file():
        try:
            data = json.loads(state_path.read_text(encoding="utf-8"))
            return str(data.get("state") or "").upper() == "OPEN"
        except Exception:
            pass
    return False


def persist_breaker_state(br: BrierCircuitBreaker, *, path: Optional[Path] = None) -> None:
    """Write breaker FSM snapshot for cross-process lockout checks."""
    p = path or Path(os.getenv("HIBS_BRIER_STATE_PATH", "/opt/hibs-bet/data/brier_circuit_state.json"))
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(br.to_dict(), indent=2), encoding="utf-8")


def run_hourly_brier_loop(
    *,
    compute_brier: Callable[[], tuple[float, int]],
    breaker: Optional[BrierCircuitBreaker] = None,
    ledger_path: Optional[Path] = None,
    domain: str = "football",
) -> Dict[str, Any]:
    """
    Active runtime circuit — call from cron hourly.

    `compute_brier` returns (mean_brier, sample_n).
    """
    br = breaker or BrierCircuitBreaker(
        threshold=float(os.getenv("HIBS_BRIER_LOCKOUT_THRESHOLD", "0.25")),
        min_samples=int(os.getenv("HIBS_BRIER_MIN_SAMPLES", "20")),
    )
    brier, n = compute_brier()
    state = br.evaluate(brier, n)
    allows, msg = br.allows_execution()
    event = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "domain": domain,
        "brier": round(brier, 5),
        "n": n,
        "state": state.value,
        "allows_execution": allows,
        "message": msg,
        "threshold": br.threshold,
    }
    lp = ledger_path or Path(
        os.getenv("HIBS_BRIER_LEDGER_PATH", "/opt/hibs-bet/data/brier_circuit_ledger")
    )
    _append_hash_chain(event, ledger_path=lp)
    persist_breaker_state(br)
    if not allows:
        os.environ["HIBS_EXECUTION_LOCKOUT"] = "1"
        os.environ["HIBS_EXECUTION_MODE"] = "diagnostic"
    elif state == BreakerState.CLOSED:
        os.environ.pop("HIBS_EXECUTION_LOCKOUT", None)
    return event


def football_brier_compute() -> tuple[float, int]:
    from hibs_predictor.prediction_log import monitor_summary_dict

    row = monitor_summary_dict()
    brier = float(row.get("brier_score_1x2") or 1.0)
    n = int(row.get("scored_n") or row.get("n_scored") or 0)
    return brier, n


def racing_place_brier_compute() -> tuple[float, int]:
    from hibs_racing.analytics.reliability_bins import place_reliability_from_ledger

    rel = place_reliability_from_ledger(backtest=False, days=60)
    return float(rel.get("brier") or 1.0), int(rel.get("n") or 0)
