"""Global kill-switches and credential vault interface."""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CircuitState(str, Enum):
    CLOSED = "closed"
    HALF_OPEN = "half_open"
    OPEN = "open"
    KILL = "kill"


@dataclass
class CircuitBreaker:
    """
    Global circuit breaker — independent of client app logic.
    KILL severs upstream; OPEN rejects new requests; HALF_OPEN allows probe traffic;
    CLOSED allows traffic.
    """

    state: CircuitState = CircuitState.CLOSED
    reason: str = ""
    failure_count: int = 0
    failure_threshold: int = 5
    half_open_probe_at: float = 0.0
    open_cooldown_sec: float = 30.0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @classmethod
    def from_env(cls) -> CircuitBreaker:
        raw = os.environ.get("INST_CIRCUIT_KILL", "").strip().lower()
        if raw in ("1", "true", "yes", "kill"):
            return cls(state=CircuitState.KILL, reason="INST_CIRCUIT_KILL env")
        threshold = int(os.environ.get("INST_CIRCUIT_FAILURE_THRESHOLD", "5") or "5")
        cooldown = float(os.environ.get("INST_CIRCUIT_OPEN_COOLDOWN_SEC", "30") or "30")
        return cls(failure_threshold=max(1, threshold), open_cooldown_sec=max(1.0, cooldown))

    def kill(self, reason: str) -> None:
        with self._lock:
            self.state = CircuitState.KILL
            self.reason = reason

    def open(self, reason: str) -> None:
        with self._lock:
            self.state = CircuitState.OPEN
            self.reason = reason
            self.half_open_probe_at = time.monotonic() + self.open_cooldown_sec

    def half_open(self, reason: str = "probe_window") -> None:
        with self._lock:
            self.state = CircuitState.HALF_OPEN
            self.reason = reason

    def close(self) -> None:
        with self._lock:
            self.state = CircuitState.CLOSED
            self.reason = ""
            self.failure_count = 0
            self.half_open_probe_at = 0.0

    def record_success(self) -> CircuitState:
        with self._lock:
            if self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.CLOSED
                self.reason = ""
                self.failure_count = 0
                self.half_open_probe_at = 0.0
            elif self.state == CircuitState.CLOSED:
                self.failure_count = 0
            return self.state

    def record_failure(self, reason: str) -> CircuitState:
        with self._lock:
            if self.state in (CircuitState.KILL, CircuitState.OPEN):
                return self.state
            self.failure_count += 1
            if self.failure_count >= self.failure_threshold:
                self.state = CircuitState.OPEN
                self.reason = reason or "failure_threshold_exceeded"
                self.half_open_probe_at = time.monotonic() + self.open_cooldown_sec
            return self.state

    def _maybe_advance_half_open(self) -> None:
        if self.state != CircuitState.OPEN:
            return
        if self.half_open_probe_at and time.monotonic() >= self.half_open_probe_at:
            self.state = CircuitState.HALF_OPEN
            self.reason = "half_open_probe"

    def allows_traffic(self) -> tuple[bool, str]:
        with self._lock:
            if self.state == CircuitState.KILL:
                return False, f"KILL: {self.reason or 'circuit killed'}"
            if self.state == CircuitState.OPEN:
                self._maybe_advance_half_open()
            if self.state == CircuitState.OPEN:
                return False, f"OPEN: {self.reason or 'circuit open'}"
            if self.state == CircuitState.HALF_OPEN:
                return True, f"HALF_OPEN: {self.reason or 'probe allowed'}"
            return True, "closed"

    def transition_snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "state": self.state.value,
                "reason": self.reason,
                "failure_count": self.failure_count,
                "failure_threshold": self.failure_threshold,
            }


@dataclass
class CredentialVault:
    """
    Gateway-held secrets — clients receive proxy tokens only.
    Production: swap for HashiCorp Vault / cloud KMS.
    """

    _secrets: dict[str, str] = field(default_factory=dict)

    def set_secret(self, key: str, value: str) -> None:
        self._secrets[key] = value

    def get_upstream_header(self, service: str) -> dict[str, str]:
        token = self._secrets.get(service, "")
        if not token:
            return {}
        return {"Authorization": f"Bearer {token}"}

    def issue_proxy_token(self, client_id: str, *, ttl_hint_sec: int = 3600) -> str:
        import hashlib

        material = f"{client_id}:{time.time()}:{ttl_hint_sec}"
        return hashlib.sha256(material.encode()).hexdigest()[:48]

    def to_dict(self) -> dict[str, Any]:
        return {"services_configured": list(self._secrets)}
