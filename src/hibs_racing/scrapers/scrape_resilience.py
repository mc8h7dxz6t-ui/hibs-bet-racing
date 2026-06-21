"""Scrape resilience for hibs-racing — circuit breaker, retry, ledger."""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, TypeVar

T = TypeVar("T")

_DEFAULT_FAILURE_THRESHOLD = 5
_DEFAULT_OPEN_SEC = 300.0


def _ledger_path() -> Path:
    cache = Path(os.getenv("HIBS_RACING_CACHE_DIR", "data/.cache"))
    return cache / "scrape_ledger.jsonl"


@dataclass
class SourceCircuit:
    source_id: str
    failure_threshold: int = _DEFAULT_FAILURE_THRESHOLD
    open_sec: float = _DEFAULT_OPEN_SEC
    consecutive_failures: int = 0
    open_until: float = 0.0
    last_error: str = ""
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def allows_traffic(self) -> tuple[bool, str]:
        ts = time.time()
        with self._lock:
            if self.open_until > ts:
                remain = max(0.0, self.open_until - ts)
                return False, f"circuit_open:{self.source_id} ({remain:.0f}s)"
        return True, "closed"

    def record_success(self) -> None:
        with self._lock:
            self.consecutive_failures = 0
            self.open_until = 0.0
            self.last_error = ""

    def record_failure(self, error: str) -> None:
        with self._lock:
            self.consecutive_failures += 1
            self.last_error = error[:200]
            if self.consecutive_failures >= self.failure_threshold:
                self.open_until = time.time() + self.open_sec


_circuits: Dict[str, SourceCircuit] = {}
_lock = threading.Lock()


def get_circuit(source_id: str) -> SourceCircuit:
    sid = (source_id or "unknown").strip().lower()
    with _lock:
        if sid not in _circuits:
            _circuits[sid] = SourceCircuit(source_id=sid)
        return _circuits[sid]


def record_ledger(source_id: str, *, ok: bool, ms: float, operation: str = "call", error: str | None = None) -> None:
    entry = {
        "at": datetime.now(timezone.utc).isoformat(),
        "source_id": source_id,
        "operation": operation,
        "ok": ok,
        "ms": round(ms, 1),
        "error": (error or "")[:160] or None,
    }
    path = _ledger_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, separators=(",", ":")) + "\n")
    except OSError:
        pass


def resilient_call(
    source_id: str,
    fn: Callable[[], T],
    *,
    operation: str = "call",
    max_retries: int = 3,
    retry_sleep_base: float = 1.5,
) -> T:
    circuit = get_circuit(source_id)
    allows, reason = circuit.allows_traffic()
    if not allows:
        raise RuntimeError(reason)

    last_exc: BaseException | None = None
    for attempt in range(max(1, max_retries)):
        t0 = time.perf_counter()
        try:
            result = fn()
            ms = (time.perf_counter() - t0) * 1000.0
            circuit.record_success()
            record_ledger(source_id, ok=True, ms=ms, operation=operation)
            return result
        except Exception as exc:
            last_exc = exc
            ms = (time.perf_counter() - t0) * 1000.0
            circuit.record_failure(str(exc))
            record_ledger(source_id, ok=False, ms=ms, operation=operation, error=str(exc))
            if attempt + 1 >= max_retries:
                break
            time.sleep(min(30.0, retry_sleep_base * (2**attempt)))
    if last_exc is not None:
        raise last_exc
    raise RuntimeError(f"{source_id}:{operation} failed")


def ledger_summary(*, max_lines: int = 100) -> dict[str, Any]:
    path = _ledger_path()
    if not path.is_file():
        return {"ok": True, "entries": 0, "sources": {}, "recent_errors": []}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()[-max_lines:]
    except OSError:
        return {"ok": False, "entries": 0, "sources": {}, "recent_errors": []}
    sources: dict[str, dict[str, int]] = {}
    recent_errors: list[dict[str, Any]] = []
    for raw in lines:
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError:
            continue
        sid = str(row.get("source_id") or "unknown")
        bucket = sources.setdefault(sid, {"ok": 0, "fail": 0})
        if row.get("ok"):
            bucket["ok"] += 1
        else:
            bucket["fail"] += 1
            if len(recent_errors) < 8:
                recent_errors.append(
                    {
                        "at": row.get("at"),
                        "source_id": sid,
                        "error": row.get("error"),
                    }
                )
    total = sum(b["ok"] + b["fail"] for b in sources.values())
    fail_n = sum(b["fail"] for b in sources.values())
    return {
        "ok": fail_n == 0 or (total > 0 and fail_n / total < 0.5),
        "entries": total,
        "sources": sources,
        "recent_errors": recent_errors,
        "ledger_path": str(path),
    }


def circuit_status() -> dict[str, Any]:
    out: dict[str, Any] = {}
    with _lock:
        items = list(_circuits.items())
    for sid, circ in items:
        ts = time.time()
        with circ._lock:
            st = "open" if circ.open_until > ts else "closed"
            allows = circ.open_until <= ts
            remain = max(0.0, circ.open_until - ts) if circ.open_until > ts else 0.0
        out[sid] = {
            "state": st,
            "allows_traffic": allows,
            "consecutive_failures": circ.consecutive_failures,
            "open_remain_sec": round(remain, 1),
            "last_error": circ.last_error or None,
        }
    return out


def scrape_resilience_status() -> dict[str, Any]:
    return {
        "ok": True,
        "circuits": circuit_status(),
        "ledger": ledger_summary(),
    }
