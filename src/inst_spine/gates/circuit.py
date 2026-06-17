"""Global kill-switches and credential vault interface."""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    KILL = "kill"


@dataclass
class CircuitBreaker:
    """
    Global circuit breaker — independent of client app logic.
    KILL severs upstream; OPEN rejects new requests; CLOSED allows traffic.
    """

    state: CircuitState = CircuitState.CLOSED
    reason: str = ""
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @classmethod
    def from_env(cls) -> CircuitBreaker:
        raw = os.environ.get("INST_CIRCUIT_KILL", "").strip().lower()
        if raw in ("1", "true", "yes", "kill"):
            return cls(state=CircuitState.KILL, reason="INST_CIRCUIT_KILL env")
        return cls()

    def kill(self, reason: str) -> None:
        with self._lock:
            self.state = CircuitState.KILL
            self.reason = reason

    def open(self, reason: str) -> None:
        with self._lock:
            self.state = CircuitState.OPEN
            self.reason = reason

    def close(self) -> None:
        with self._lock:
            self.state = CircuitState.CLOSED
            self.reason = ""

    def allows_traffic(self) -> tuple[bool, str]:
        with self._lock:
            if self.state == CircuitState.KILL:
                return False, f"KILL: {self.reason or 'circuit killed'}"
            if self.state == CircuitState.OPEN:
                return False, f"OPEN: {self.reason or 'circuit open'}"
            return True, "closed"


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
        import time

        material = f"{client_id}:{time.time()}:{ttl_hint_sec}"
        return hashlib.sha256(material.encode()).hexdigest()[:48]

    def to_dict(self) -> dict[str, Any]:
        return {"services_configured": list(self._secrets)}
