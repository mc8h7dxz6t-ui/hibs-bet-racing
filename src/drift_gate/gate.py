"""Drift gate — PSI/KS evaluation with shadow and enforce modes."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from drift_gate.baseline import FeatureBaseline
from drift_gate.stats import compute_ks_statistic, compute_psi, ks_critical_value, psi_band


class DriftGateMode(str, Enum):
    SHADOW = "shadow"
    ENFORCE = "enforce"


class DriftGateDecision(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"
    KILL = "kill"


@dataclass
class DriftGateConfig:
    psi_warn: float = 0.1
    psi_reject: float = 0.25
    ks_alpha: float = 0.05
    bins: int = 10
    min_baseline_samples: int = 30
    min_current_samples: int = 5
    mode: DriftGateMode = DriftGateMode.SHADOW


@dataclass
class DriftGateRequest:
    model_id: str
    version: str
    feature_vector: dict[str, float]
    request_id: str = ""


@dataclass
class FeatureDriftReport:
    feature: str
    psi: float
    psi_band: str
    ks_d: float
    ks_exceeded: bool
    baseline_n: int
    current_n: int


@dataclass
class DriftGateResponse:
    decision: DriftGateDecision
    reason: str
    mode: DriftGateMode
    reports: list[FeatureDriftReport] = field(default_factory=list)
    shadow_would_reject: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.value,
            "reason": self.reason,
            "mode": self.mode.value,
            "shadow_would_reject": self.shadow_would_reject,
            "reports": [
                {
                    "feature": r.feature,
                    "psi": round(r.psi, 6),
                    "psi_band": r.psi_band,
                    "ks_d": round(r.ks_d, 6),
                    "ks_exceeded": r.ks_exceeded,
                    "baseline_n": r.baseline_n,
                    "current_n": r.current_n,
                }
                for r in self.reports
            ],
        }


class DriftGate:
    """
    Compare live feature vectors against a stored baseline.
    Shadow mode logs drift but always APPROVEs; enforce mode REJECTs/KILLs.
    """

    def __init__(
        self,
        baseline: FeatureBaseline,
        *,
        config: DriftGateConfig | None = None,
        rolling_window: dict[str, list[float]] | dict[str, deque[float]] | None = None,
    ) -> None:
        self.baseline = baseline
        self.config = config or DriftGateConfig()
        self._rolling: dict[str, list[float]] = rolling_window or {}

    def _rolling_for(self, feature: str) -> deque[float]:
        if feature not in self._rolling:
            self._rolling[feature] = deque(maxlen=self.config.min_baseline_samples * 4)
        raw = self._rolling[feature]
        if isinstance(raw, list):
            self._rolling[feature] = deque(raw, maxlen=self.config.min_baseline_samples * 4)
        return self._rolling[feature]  # type: ignore[return-value]

    def evaluate(self, req: DriftGateRequest) -> DriftGateResponse:
        cfg = self.config
        if not FeatureBaseline.validate_version_compatibility(req.version, self.baseline.version):
            return DriftGateResponse(
                decision=DriftGateDecision.REJECT if cfg.mode == DriftGateMode.ENFORCE else DriftGateDecision.APPROVE,
                reason=f"baseline_version_incompatible: request={req.version} baseline={self.baseline.version}",
                mode=cfg.mode,
                reports=[],
                shadow_would_reject=cfg.mode == DriftGateMode.ENFORCE,
            )

        reports: list[FeatureDriftReport] = []
        worst_psi = 0.0
        any_ks = False
        missing_baseline_features: list[str] = []
        invalid_features: list[str] = []

        baseline_feature_names = set(self.baseline.features.keys())

        for name in sorted(baseline_feature_names):
            if name not in req.feature_vector:
                missing_baseline_features.append(name)

        for name, value in req.feature_vector.items():
            if value is None:
                invalid_features.append(name)
                continue
            try:
                v = float(value)
            except (TypeError, ValueError):
                invalid_features.append(name)
                continue
            self._rolling_for(name).append(v)
            base_samples = self.baseline.features.get(name, [])
            cur_samples = self._rolling_for(name)
            if len(base_samples) < cfg.min_baseline_samples:
                continue
            if len(cur_samples) < cfg.min_current_samples:
                continue

            psi = compute_psi(base_samples, cur_samples, bins=cfg.bins)
            ks_d = compute_ks_statistic(base_samples, cur_samples)
            ks_crit = ks_critical_value(cfg.ks_alpha)
            ks_exceeded = ks_d > ks_crit
            reports.append(
                FeatureDriftReport(
                    feature=name,
                    psi=psi,
                    psi_band=psi_band(psi),
                    ks_d=ks_d,
                    ks_exceeded=ks_exceeded,
                    baseline_n=len(base_samples),
                    current_n=len(cur_samples),
                )
            )
            worst_psi = max(worst_psi, psi)
            any_ks = any_ks or ks_exceeded

        if missing_baseline_features or invalid_features:
            detail_parts: list[str] = []
            if missing_baseline_features:
                detail_parts.append(f"missing={','.join(missing_baseline_features)}")
            if invalid_features:
                detail_parts.append(f"invalid={','.join(invalid_features)}")
            reason = "feature_contract_violation:" + ";".join(detail_parts)
            if cfg.mode == DriftGateMode.ENFORCE:
                return DriftGateResponse(
                    decision=DriftGateDecision.REJECT,
                    reason=reason,
                    mode=cfg.mode,
                    reports=reports,
                    shadow_would_reject=True,
                )
            return DriftGateResponse(
                decision=DriftGateDecision.APPROVE,
                reason=f"shadow:{reason}",
                mode=cfg.mode,
                reports=reports,
                shadow_would_reject=True,
            )

        would_reject = worst_psi >= cfg.psi_reject or any_ks
        would_warn = worst_psi >= cfg.psi_warn

        if not reports:
            return DriftGateResponse(
                decision=DriftGateDecision.APPROVE,
                reason="insufficient_samples_for_drift_test",
                mode=cfg.mode,
                reports=reports,
                shadow_would_reject=False,
            )

        if would_reject:
            reason = f"drift: psi>={cfg.psi_reject:.2f} or ks_exceeded (worst_psi={worst_psi:.4f})"
            if cfg.mode == DriftGateMode.ENFORCE:
                decision = DriftGateDecision.KILL if worst_psi >= cfg.psi_reject * 1.5 else DriftGateDecision.REJECT
                return DriftGateResponse(
                    decision=decision,
                    reason=reason,
                    mode=cfg.mode,
                    reports=reports,
                    shadow_would_reject=True,
                )
            return DriftGateResponse(
                decision=DriftGateDecision.APPROVE,
                reason=f"shadow:{reason}",
                mode=cfg.mode,
                reports=reports,
                shadow_would_reject=True,
            )

        if would_warn:
            return DriftGateResponse(
                decision=DriftGateDecision.APPROVE,
                reason=f"drift_watch: worst_psi={worst_psi:.4f}",
                mode=cfg.mode,
                reports=reports,
                shadow_would_reject=False,
            )

        return DriftGateResponse(
            decision=DriftGateDecision.APPROVE,
            reason="drift_stable",
            mode=cfg.mode,
            reports=reports,
            shadow_would_reject=False,
        )
