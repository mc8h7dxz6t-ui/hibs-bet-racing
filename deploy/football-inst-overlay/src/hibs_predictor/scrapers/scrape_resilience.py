"""Inst++ scrape resilience — per-source circuit breaker, retry, and telemetry ledger.

Wraps outbound scraper HTTP and callable paths so cron/hands-off cycles degrade
gracefully (stale cache, skip open circuits) instead of hammering blocked sources.
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, TypeVar

from hibs_predictor.app_logging import get_logger, log_resilience_event
from hibs_predictor.scraper_health import http_status_from_exc, scraper_error_code

_log = get_logger("scrape_resilience")
T = TypeVar("T")

_DEFAULT_FAILURE_THRESHOLD = 5
_DEFAULT_OPEN_SEC = 300.0
_DEFAULT_HALF_OPEN_SEC = 60.0
_LEDGER_MAX_LINES = 500


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _ledger_path() -> Path:
    cache_dir = Path(os.getenv("HIBS_CACHE_DIR", ".cache"))
    return cache_dir / "scrape_ledger.jsonl"


@dataclass
class SourceCircuit:
    """Per-source circuit: CLOSED → OPEN after failure streak → HALF_OPEN probe."""

    source_id: str
    failure_threshold: int = _DEFAULT_FAILURE_THRESHOLD
    open_sec: float = _DEFAULT_OPEN_SEC
    half_open_sec: float = _DEFAULT_HALF_OPEN_SEC
    consecutive_failures: int = 0
    open_until: float = 0.0
    last_success_at: float = 0.0
    last_error: str = ""
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def state(self, now: Optional[float] = None) -> str:
        ts = now if now is not None else time.time()
        with self._lock:
            if self.open_until > ts:
                return "open"
            if self.consecutive_failures >= self.failure_threshold and self.last_success_at > 0:
                if ts - self.last_success_at < self.half_open_sec:
                    return "half_open"
            return "closed"

    def allows_traffic(self) -> tuple[bool, str]:
        ts = time.time()
        st = self.state(ts)
        if st == "open":
            with self._lock:
                remain = max(0.0, self.open_until - ts)
                err = self.last_error[:80] if self.last_error else "failures"
            return False, f"circuit_open:{self.source_id} ({remain:.0f}s) {err}"
        return True, st

    def record_success(self) -> None:
        with self._lock:
            self.consecutive_failures = 0
            self.open_until = 0.0
            self.last_success_at = time.time()
            self.last_error = ""

    def record_failure(self, error: str, *, http_status: Optional[int] = None) -> None:
        with self._lock:
            self.consecutive_failures += 1
            self.last_error = error[:200]
            if http_status in (403, 429, 451) or self.consecutive_failures >= self.failure_threshold:
                self.open_until = time.time() + self.open_sec


_circuits: Dict[str, SourceCircuit] = {}
_circuits_lock = threading.Lock()


def get_circuit(source_id: str) -> SourceCircuit:
    sid = (source_id or "unknown").strip().lower()
    with _circuits_lock:
        if sid not in _circuits:
            _circuits[sid] = SourceCircuit(
                source_id=sid,
                failure_threshold=_env_int("HIBS_SCRAPE_CIRCUIT_FAILURES", _DEFAULT_FAILURE_THRESHOLD),
                open_sec=_env_float("HIBS_SCRAPE_CIRCUIT_OPEN_SEC", _DEFAULT_OPEN_SEC),
            )
        return _circuits[sid]


def circuit_status() -> Dict[str, Any]:
    now = time.time()
    out: Dict[str, Any] = {}
    with _circuits_lock:
        items = list(_circuits.items())
    for sid, circ in items:
        st = circ.state(now)
        allows, detail = circ.allows_traffic()
        out[sid] = {
            "state": st,
            "allows_traffic": allows,
            "detail": detail,
            "consecutive_failures": circ.consecutive_failures,
            "last_error": circ.last_error or None,
        }
    return out


def record_ledger(
    source_id: str,
    *,
    ok: bool,
    ms: float,
    operation: str = "call",
    error: Optional[str] = None,
    error_code: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    entry = {
        "at": datetime.now(timezone.utc).isoformat(),
        "source_id": source_id,
        "operation": operation,
        "ok": ok,
        "ms": round(ms, 1),
        "error": (error or "")[:160] or None,
        "error_code": error_code,
    }
    if extra:
        entry.update(extra)
    path = _ledger_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, separators=(",", ":")) + "\n")
        _trim_ledger(path)
    except OSError:
        pass
    log_resilience_event(
        _log,
        "scrape_ledger",
        source=source_id,
        ok=ok,
        ms=round(ms, 1),
        operation=operation,
        error_code=error_code,
    )


def _trim_ledger(path: Path) -> None:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        if len(lines) <= _LEDGER_MAX_LINES:
            return
        path.write_text("\n".join(lines[-_LEDGER_MAX_LINES:]) + "\n", encoding="utf-8")
    except OSError:
        pass


def ledger_summary(*, max_lines: int = 200) -> Dict[str, Any]:
    path = _ledger_path()
    if not path.is_file():
        return {"ok": True, "entries": 0, "sources": {}, "recent_errors": []}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()[-max_lines:]
    except OSError:
        return {"ok": False, "entries": 0, "sources": {}, "recent_errors": []}

    sources: Dict[str, Dict[str, int]] = {}
    recent_errors: List[Dict[str, Any]] = []
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
                        "error_code": row.get("error_code"),
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


def resilient_call(
    source_id: str,
    fn: Callable[[], T],
    *,
    operation: str = "call",
    max_retries: int = 3,
    retry_sleep_base: float = 1.0,
    fallback: Optional[Callable[[], T]] = None,
    skip_if_open: bool = True,
) -> T:
    """Run ``fn`` with circuit guard, retries, and ledger telemetry."""
    circuit = get_circuit(source_id)
    if skip_if_open:
        allows, reason = circuit.allows_traffic()
        if not allows:
            if fallback is not None:
                return fallback()
            raise RuntimeError(reason)

    last_exc: Optional[BaseException] = None
    retries = max(1, max_retries)
    for attempt in range(retries):
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
            http_status = http_status_from_exc(exc)
            code = scraper_error_code(
                ok=False,
                blocked=http_status in (403, 429, 451),
                http_status=http_status,
                layout_broken="no odds table" in str(exc).lower() or "eventtable" in str(exc).lower(),
            )
            circuit.record_failure(str(exc), http_status=http_status)
            record_ledger(
                source_id,
                ok=False,
                ms=ms,
                operation=operation,
                error=str(exc),
                error_code=code,
            )
            if attempt + 1 >= retries:
                break
            time.sleep(min(30.0, retry_sleep_base * (2**attempt)))

    if fallback is not None:
        return fallback()
    if last_exc is not None:
        raise last_exc
    raise RuntimeError(f"{source_id}:{operation} failed")


def resilient_http_get(
    source_id: str,
    url: str,
    *,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
    timeout: float = 20.0,
    max_retries: int = 3,
) -> Any:
    """``requests.get`` with resilience wrapper; returns Response."""
    import requests

    def _do():
        resp = requests.get(url, headers=headers or {}, params=params or {}, timeout=timeout)
        if resp.status_code in (429, 503):
            resp.raise_for_status()
        if resp.status_code >= 400:
            resp.raise_for_status()
        return resp

    return resilient_call(source_id, _do, operation="http_get", max_retries=max_retries)


def scrape_resilience_status() -> Dict[str, Any]:
    return {
        "ok": True,
        "circuits": circuit_status(),
        "ledger": ledger_summary(),
    }
