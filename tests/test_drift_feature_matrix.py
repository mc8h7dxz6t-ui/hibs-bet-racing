"""Drift gate — null/missing feature matrix (Wave 1)."""

from __future__ import annotations

import pytest

from drift_gate.baseline import BASELINE_SCHEMA_VERSION, FeatureBaseline
from drift_gate.gate import DriftGate, DriftGateConfig, DriftGateDecision, DriftGateMode, DriftGateRequest


def _baseline() -> FeatureBaseline:
    bl = FeatureBaseline(model_id="m1", version="2.0.0")
    samples = [float(i) for i in range(40)]
    bl.features = {"f1": samples, "f2": samples}
    bl.baseline_schema_version = BASELINE_SCHEMA_VERSION
    return bl


def test_missing_baseline_feature_enforce_rejects():
    gate = DriftGate(_baseline(), config=DriftGateConfig(mode=DriftGateMode.ENFORCE))
    resp = gate.evaluate(
        DriftGateRequest(model_id="m1", version="2.0.0", feature_vector={"f1": 1.0})
    )
    assert resp.decision == DriftGateDecision.REJECT
    assert "missing=f2" in resp.reason


def test_null_feature_enforce_rejects():
    gate = DriftGate(_baseline(), config=DriftGateConfig(mode=DriftGateMode.ENFORCE))
    resp = gate.evaluate(
        DriftGateRequest(
            model_id="m1",
            version="2.0.0",
            feature_vector={"f1": 1.0, "f2": None},
        )
    )
    assert resp.decision == DriftGateDecision.REJECT
    assert "invalid=f2" in resp.reason


def test_incompatible_baseline_version_enforce_rejects():
    gate = DriftGate(_baseline(), config=DriftGateConfig(mode=DriftGateMode.ENFORCE))
    resp = gate.evaluate(
        DriftGateRequest(model_id="m1", version="9.0.0", feature_vector={"f1": 1.0, "f2": 2.0})
    )
    assert resp.decision == DriftGateDecision.REJECT
    assert "baseline_version_incompatible" in resp.reason


def test_unsupported_schema_version_raises():
    with pytest.raises(ValueError, match="unsupported baseline_schema_version"):
        FeatureBaseline.from_dict({"baseline_schema_version": "99.0", "model_id": "x", "version": "1"})
