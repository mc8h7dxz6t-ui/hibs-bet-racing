"""Golden-file PSI/KS regression — Wave 1 drift gate hardening."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from drift_gate.stats import compute_ks_statistic, compute_psi, psi_band

GOLDEN = Path(__file__).parent / "golden" / "drift_stats.json"


@pytest.fixture
def golden_data() -> dict:
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


def test_golden_psi_stable(golden_data: dict):
    case = golden_data["psi_stable"]
    psi = compute_psi(case["baseline"], case["current"], bins=case.get("bins", 10))
    assert psi == pytest.approx(case["expected_psi"], abs=case.get("tolerance", 0.02))
    assert psi_band(psi) == case["expected_band"]


def test_golden_psi_significant(golden_data: dict):
    case = golden_data["psi_significant"]
    psi = compute_psi(case["baseline"], case["current"], bins=case.get("bins", 10))
    assert psi >= case["min_psi"]
    assert psi_band(psi) == case["expected_band"]


def test_golden_ks_shift(golden_data: dict):
    case = golden_data["ks_shift"]
    d = compute_ks_statistic(case["baseline"], case["current"])
    assert d == pytest.approx(case["expected_d"], abs=case.get("tolerance", 0.05))


def test_golden_psi_identical_near_zero(golden_data: dict):
    case = golden_data["psi_identical"]
    psi = compute_psi(case["baseline"], case["current"])
    assert psi < case["max_psi"]
    assert psi_band(psi) == "stable"
