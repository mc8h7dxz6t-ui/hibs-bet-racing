"""Tests for Drift Gate — PSI/KS statistics and gate evaluation."""

from __future__ import annotations

from pathlib import Path

import pytest

from drift_gate.baseline import FeatureBaseline
from drift_gate.gate import DriftGate, DriftGateConfig, DriftGateMode, DriftGateRequest
from drift_gate.record import record_drift_evaluation
from drift_gate.stats import compute_ks_statistic, compute_psi, psi_band


def test_psi_stable_distribution_near_zero():
    baseline = [100.0 + (i % 5) for i in range(100)]
    current = [100.0 + (i % 5) for i in range(50)]
    psi = compute_psi(baseline, current)
    assert psi < 0.1
    assert psi_band(psi) == "stable"


def test_psi_significant_on_shifted_distribution():
    baseline = [float(i) for i in range(100)]
    current = [float(i) + 50.0 for i in range(100)]
    psi = compute_psi(baseline, current)
    assert psi > 0.25
    assert psi_band(psi) == "significant"


def test_ks_detects_shift():
    baseline = [1.0, 2.0, 3.0, 4.0, 5.0] * 20
    current = [10.0, 11.0, 12.0, 13.0, 14.0] * 20
    d = compute_ks_statistic(baseline, current)
    assert d > 0.5


def test_drift_gate_shadow_approves_on_drift(tmp_path: Path):
    bl = FeatureBaseline(model_id="m1", version="v1")
    bl.features["income"] = [50000.0 + (i % 10) * 100 for i in range(50)]
    bl.features["debt_ratio"] = [0.35 + (i % 5) * 0.01 for i in range(50)]
    gate = DriftGate(
        bl,
        config=DriftGateConfig(mode=DriftGateMode.SHADOW, min_current_samples=3),
    )
    for _ in range(3):
        gate.evaluate(DriftGateRequest(model_id="m1", version="v1", feature_vector={"income": 50000, "debt_ratio": 0.35}))
    resp = gate.evaluate(
        DriftGateRequest(
            model_id="m1",
            version="v1",
            feature_vector={"income": 200000, "debt_ratio": 0.95},
        )
    )
    assert resp.decision.value == "approve"
    assert resp.shadow_would_reject or resp.reason.startswith("shadow:")


def test_drift_gate_enforce_rejects_on_drift(tmp_path: Path):
    bl = FeatureBaseline(model_id="m1", version="v1")
    bl.features["score"] = [float(i) for i in range(50)]
    gate = DriftGate(
        bl,
        config=DriftGateConfig(mode=DriftGateMode.ENFORCE, min_current_samples=3, psi_reject=0.1),
    )
    gate._rolling["score"] = [1.0, 2.0, 3.0, 2.5, 3.5]
    resp = gate.evaluate(
        DriftGateRequest(model_id="m1", version="v1", feature_vector={"score": 100.0})
    )
    assert resp.decision.value in ("reject", "kill")


def test_drift_gate_records_to_ledger(tmp_path: Path):
    db = tmp_path / "drift.sqlite"
    bl = FeatureBaseline(model_id="m1", version="v1")
    bl.features["x"] = [1.0] * 40
    gate = DriftGate(bl, config=DriftGateConfig(min_current_samples=1, min_baseline_samples=10))
    req = DriftGateRequest(model_id="m1", version="v1", feature_vector={"x": 1.0})
    resp = gate.evaluate(req)
    entry = record_drift_evaluation(request=req, response=resp, database=db)
    assert entry["event_type"] == "drift_gate_evaluation"
