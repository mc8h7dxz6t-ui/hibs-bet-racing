"""Runtime Brier calibration circuit breaker — OPEN / HALF_OPEN / CLOSED + hash chain."""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

DOMAINS = ("football", "racing")


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


def _data_root() -> Path:
    return Path(os.getenv("HIBS_BRIER_DATA_DIR", "/opt/hibs-bet/data"))


def domain_state_path(domain: str) -> Path:
    override = os.getenv(f"HIBS_BRIER_STATE_PATH_{domain.upper()}", "").strip()
    if override:
        return Path(override)
    legacy = os.getenv("HIBS_BRIER_STATE_PATH", "").strip()
    if legacy and domain == "football":
        return Path(legacy)
    return _data_root() / f"brier_circuit_state_{domain}.json"


def combined_state_path() -> Path:
    return _data_root() / "brier_circuit_state.json"


def _state_blocks_execution(state: str) -> bool:
    return str(state or "").upper() in ("OPEN", "HALF_OPEN")


def read_domain_state(domain: str) -> Dict[str, Any]:
    path = domain_state_path(domain)
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def calibration_safety_summary() -> Dict[str, Any]:
    """Unified operator view across football + racing breakers."""
    domains: Dict[str, Any] = {}
    any_lockout = False
    for domain in DOMAINS:
        row = read_domain_state(domain)
        state = str(row.get("state") or "UNKNOWN").upper()
        locked = _state_blocks_execution(state)
        any_lockout = any_lockout or locked
        domains[domain] = {
            **row,
            "state": state,
            "execution_locked": locked,
            "state_path": str(domain_state_path(domain)),
        }
    return {
        "execution_lockout_active": any_lockout,
        "domains": domains,
        "combined_state_path": str(combined_state_path()),
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


def execution_lockout_active(*, domain: Optional[str] = None) -> bool:
    """True when hourly Brier circuit breaker blocks execution (OPEN or HALF_OPEN)."""
    flag = (os.getenv("HIBS_EXECUTION_LOCKOUT") or "").strip().lower()
    if flag in ("1", "true", "yes", "on"):
        return True
    targets = [domain] if domain else list(DOMAINS)
    for dom in targets:
        if not dom:
            continue
        row = read_domain_state(dom)
        if _state_blocks_execution(str(row.get("state") or "")):
            return True
    # Legacy single-file fallback
    legacy = Path(os.getenv("HIBS_BRIER_STATE_PATH", "/opt/hibs-bet/data/brier_circuit_state.json"))
    if legacy.is_file() and domain is None:
        try:
            data = json.loads(legacy.read_text(encoding="utf-8"))
            if _state_blocks_execution(str(data.get("state") or "")):
                return True
            if isinstance(data.get("domains"), dict):
                for row in data["domains"].values():
                    if _state_blocks_execution(str((row or {}).get("state") or "")):
                        return True
        except Exception:
            pass
    return False


def persist_breaker_state(
    br: BrierCircuitBreaker,
    *,
    domain: str,
    path: Optional[Path] = None,
) -> None:
    """Write per-domain FSM snapshot + combined index for cross-process checks."""
    p = path or domain_state_path(domain)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {**br.to_dict(), "domain": domain, "updated_at": datetime.now(timezone.utc).isoformat()}
    p.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    combined = combined_state_path()
    index: Dict[str, Any] = {}
    if combined.is_file():
        try:
            index = json.loads(combined.read_text(encoding="utf-8"))
        except Exception:
            index = {}
    if not isinstance(index.get("domains"), dict):
        index["domains"] = {}
    index["domains"][domain] = payload
    index["execution_lockout_active"] = execution_lockout_active()
    index["updated_at"] = datetime.now(timezone.utc).isoformat()
    combined.write_text(json.dumps(index, indent=2), encoding="utf-8")


def run_hourly_brier_loop(
    *,
    compute_brier: Callable[[], tuple[float, int]],
    breaker: Optional[BrierCircuitBreaker] = None,
    ledger_path: Optional[Path] = None,
    domain: str = "football",
    state_path: Optional[Path] = None,
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
    chain = _append_hash_chain(event, ledger_path=lp)
    event["ledger"] = chain
    persist_breaker_state(br, domain=domain, path=state_path)
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
