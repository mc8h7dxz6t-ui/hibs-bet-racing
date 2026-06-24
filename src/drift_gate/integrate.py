"""Integration hooks for Proxy-Risk and ModelGovernor."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from drift_gate.baseline import FeatureBaseline
from drift_gate.gate import DriftGate, DriftGateConfig, DriftGateMode, DriftGateRequest
from drift_gate.record import record_drift_evaluation


def evaluate_model_features(
    *,
    model_id: str,
    version: str,
    features: dict[str, float],
    baseline_path: Path,
    mode: str = "shadow",
    database: Path | None = None,
    request_id: str = "",
) -> dict[str, Any]:
    """
    Drop-in hook: load baseline, evaluate drift, optionally record to ledger.
    Use from Proxy-Risk middleware or ModelGovernor deploy gate.
    """
    baseline = FeatureBaseline.load(baseline_path)
    gate = DriftGate(
        baseline,
        config=DriftGateConfig(mode=DriftGateMode(mode)),
    )
    req = DriftGateRequest(
        model_id=model_id,
        version=version,
        feature_vector=features,
        request_id=request_id,
    )
    resp = gate.evaluate(req)
    entry = record_drift_evaluation(request=req, response=resp, database=database)
    return {"response": resp.to_dict(), "ledger_entry": entry}
