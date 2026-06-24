"""Baseline feature distributions for drift comparison."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class FeatureBaseline:
    """Rolling baseline samples per numeric feature."""

    model_id: str
    version: str
    features: dict[str, list[float]] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_sample(self, feature_vector: dict[str, float]) -> None:
        for name, value in feature_vector.items():
            try:
                v = float(value)
            except (TypeError, ValueError):
                continue
            self.features.setdefault(name, []).append(v)

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "version": self.version,
            "features": self.features,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FeatureBaseline:
        return cls(
            model_id=str(data.get("model_id") or "default"),
            version=str(data.get("version") or "v1"),
            features={k: [float(x) for x in v] for k, v in (data.get("features") or {}).items()},
            metadata=dict(data.get("metadata") or {}),
        )

    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> FeatureBaseline:
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
