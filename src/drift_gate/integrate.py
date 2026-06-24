"""Integration hooks for Proxy-Risk and ModelGovernor."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from drift_gate.baseline import FeatureBaseline
from drift_gate.gate import DriftGate, DriftGateConfig, DriftGateMode, DriftGateRequest
from drift_gate.record import record_drift_evaluation
from drift_gate.state import RollingStateStore

# Stateful integrate cache — rolling burn-in survives between hook calls.
_GATE_CACHE: dict[str, tuple[DriftGate, RollingStateStore | None]] = {}


def _cache_key(baseline_path: Path, mode: str) -> str:
    return f"{baseline_path.resolve()}:{mode}"


def clear_integrate_cache() -> None:
    """Test helper — reset cached gates."""
    _GATE_CACHE.clear()


def evaluate_model_features(
    *,
    model_id: str,
    version: str,
    features: dict[str, float],
    baseline_path: Path,
    mode: str = "shadow",
    database: Path | None = None,
    request_id: str = "",
    state_path: Path | None = None,
) -> dict[str, Any]:
    """
    Drop-in hook: load baseline, evaluate drift with persistent rolling state,
    optionally record to ledger. Use from Proxy-Risk middleware or ModelGovernor deploy gate.
    """
    baseline_path = Path(baseline_path)
    cache_key = _cache_key(baseline_path, mode)
    if cache_key not in _GATE_CACHE:
        baseline = FeatureBaseline.load(baseline_path)
        rolling = RollingStateStore.from_baseline(
            baseline_path,
            state_path=state_path,
            redis_key=f"integrate:{baseline.model_id}:{mode}",
        )
        gate = DriftGate(
            baseline,
            config=DriftGateConfig(mode=DriftGateMode(mode)),
            rolling_window=rolling.as_dict(),
        )
        _GATE_CACHE[cache_key] = (gate, rolling)
    gate, rolling = _GATE_CACHE[cache_key]

    req = DriftGateRequest(
        model_id=model_id,
        version=version,
        feature_vector=features,
        request_id=request_id,
    )
    resp = gate.evaluate(req)
    if rolling is not None:
        rolling._data = gate._rolling
        rolling.save()

    entry = record_drift_evaluation(request=req, response=resp, database=database)
    return {"response": resp.to_dict(), "ledger_entry": entry}
