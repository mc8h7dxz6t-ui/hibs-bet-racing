"""Persistent rolling feature windows — file or Redis (multi-instance)."""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class RollingStateBackend(ABC):
    @abstractmethod
    def as_dict(self) -> dict[str, list[float]]:
        ...

    @abstractmethod
    def replace(self, data: dict[str, list[float]]) -> None:
        ...

    @abstractmethod
    def save(self) -> None:
        ...


class FileRollingStateBackend(RollingStateBackend):
    """File-backed rolling samples — survives CLI restarts."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._data: dict[str, list[float]] = {}
        if self.path.is_file():
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            self._data = {k: [float(x) for x in v] for k, v in (raw.get("features") or {}).items()}

    def as_dict(self) -> dict[str, list[float]]:
        return {k: list(v) for k, v in self._data.items()}

    def replace(self, data: dict[str, list[float]]) -> None:
        self._data = {k: list(v) for k, v in data.items()}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({"features": self._data}, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    @classmethod
    def default_path_for(cls, baseline: Path) -> Path:
        return baseline.with_suffix(".rolling.json")


class RedisRollingStateBackend(RollingStateBackend):
    """Redis-backed rolling windows for multi-instance drift-gate."""

    def __init__(self, redis_url: str, *, key: str) -> None:
        try:
            import redis
        except ImportError as exc:
            raise RuntimeError("Redis rolling state requires: pip install redis") from exc
        self._client = redis.from_url(redis_url, decode_responses=True)
        self._key = f"inst:drift:rolling:{key}"

    def as_dict(self) -> dict[str, list[float]]:
        raw = self._client.get(self._key)
        if not raw:
            return {}
        data = json.loads(raw)
        return {k: [float(x) for x in v] for k, v in (data.get("features") or {}).items()}

    def replace(self, data: dict[str, list[float]]) -> None:
        self._client.set(self._key, json.dumps({"features": data}, sort_keys=True))

    def save(self) -> None:
        return None


class RollingStateStore:
    """Facade — file default; Redis when INST_REDIS_URL set and key provided."""

    def __init__(self, backend: RollingStateBackend) -> None:
        self._backend = backend

    def append(self, feature_vector: dict[str, float], *, max_window: int = 100) -> None:
        data = self._backend.as_dict()
        for name, value in feature_vector.items():
            try:
                v = float(value)
            except (TypeError, ValueError):
                continue
            buf = data.setdefault(name, [])
            buf.append(v)
            if len(buf) > max_window:
                del buf[: len(buf) - max_window]
        self._backend.replace(data)

    def as_dict(self) -> dict[str, list[float]]:
        return self._backend.as_dict()

    def save(self) -> None:
        self._backend.save()

    @property
    def _data(self) -> dict[str, list[float]]:
        return self._backend.as_dict()

    @_data.setter
    def _data(self, value: dict[str, list[float]]) -> None:
        self._backend.replace(value)

    @classmethod
    def from_baseline(
        cls,
        baseline_path: Path,
        *,
        state_path: Path | None = None,
        redis_key: str | None = None,
    ) -> RollingStateStore:
        from inst_spine.production_profile import drift_redis_rolling_required

        url = os.environ.get("INST_REDIS_URL", "").strip()
        if drift_redis_rolling_required() and not (url and redis_key):
            raise RuntimeError(
                "INST_REDIS_URL and redis_key required for drift rolling state in production profile"
            )
        if url and redis_key:
            return cls(RedisRollingStateBackend(url, key=redis_key))
        path = state_path or FileRollingStateBackend.default_path_for(baseline_path)
        return cls(FileRollingStateBackend(path))

    @classmethod
    def default_path_for(cls, baseline: Path) -> Path:
        return FileRollingStateBackend.default_path_for(baseline)
