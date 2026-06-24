"""Persistent rolling feature windows for multi-invocation drift evaluation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class RollingStateStore:
    """File-backed rolling samples — survives CLI restarts and integrates with baselines."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._data: dict[str, list[float]] = {}
        if self.path.is_file():
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            self._data = {k: [float(x) for x in v] for k, v in (raw.get("features") or {}).items()}

    def append(self, feature_vector: dict[str, float], *, max_window: int = 100) -> None:
        for name, value in feature_vector.items():
            try:
                v = float(value)
            except (TypeError, ValueError):
                continue
            buf = self._data.setdefault(name, [])
            buf.append(v)
            if len(buf) > max_window:
                del buf[: len(buf) - max_window]

    def as_dict(self) -> dict[str, list[float]]:
        return {k: list(v) for k, v in self._data.items()}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({"features": self._data}, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    @classmethod
    def default_path_for(cls, baseline: Path) -> Path:
        return baseline.with_suffix(".rolling.json")
