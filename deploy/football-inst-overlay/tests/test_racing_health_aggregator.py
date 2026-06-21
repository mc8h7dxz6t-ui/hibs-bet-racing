"""Inst++ racing health aggregator — HTTP-only merge tests."""

from __future__ import annotations

import json

import pytest

from hibs_predictor import racing_evidence as re
from hibs_predictor.racing_health_aggregator import (
    _merge_health,
    build_institutional_racing_health,
    normalize_racing_health,
    racing_health_url,
)


def test_racing_health_url_full():
    url = racing_health_url(full=True)
    assert "/api/health" in url
    assert "full=1" in url


def test_normalize_derives_recon_and_paper():
    health = {
        "runners_loaded": 50,
        "scores_loaded": 50,
        "unscored_runners": 0,
        "nan_integrity_passed": True,
        "db_ui_in_sync": True,
        "snapshot_coverage_pct": 62.5,
        "paper": {"n_rows": 40, "settled": 35},
    }
    out = normalize_racing_health(health)
    assert out["telemetry_balance"]["coverage_pct"] == 62.5
    assert out["recon_clean"] is True
    assert out["paper"]["n_rows"] == 40


def test_merge_fills_gaps_only():
    primary = {"runners_loaded": 100, "paper_recon_clean": True}
    fallback = {
        "snapshot_coverage_pct": 55.0,
        "paper": {"n_rows": 30},
    }
    merged = _merge_health(primary, fallback)
    assert merged["telemetry_balance"]["coverage_pct"] == 55.0
    assert merged["recon_clean"] is True
    assert merged["paper"]["n_rows"] == 30


def test_merge_primary_wins():
    primary = {
        "telemetry_balance": {"coverage_pct": 80.0},
        "recon_clean": False,
        "paper": {"n_rows": 5},
    }
    fallback = {
        "snapshot_coverage_pct": 40.0,
        "paper": {"n_rows": 99},
    }
    merged = _merge_health(primary, fallback)
    assert merged["telemetry_balance"]["coverage_pct"] == 80.0
    assert merged["recon_clean"] is False
    assert merged["paper"]["n_rows"] == 5


def test_evidence_gates_use_http_health(monkeypatch):
    def fake_get(url: str, *, timeout: float = 20.0):
        if url.endswith("/api/ping"):
            return 200, '{"revision":"x"}'
        if url.endswith("/cards"):
            return 200, "<html><body>race card runner</body></html>" * 50
        if "/api/health" in url:
            return 200, json.dumps(
                {
                    "runners_loaded": 20,
                    "scores_loaded": 20,
                    "unscored_runners": 0,
                    "nan_integrity_passed": True,
                    "db_ui_in_sync": True,
                    "snapshot_coverage_pct": 75.0,
                    "paper": {"n_rows": 30, "settled": 28},
                }
            )
        if "portfolio" in url:
            return 200, "{}"
        return 404, ""

    monkeypatch.setattr(re, "_http_get", fake_get)
    monkeypatch.setenv("HIBS_PRODUCTION", "1")
    rep = re.racing_evidence_gates()
    r5 = next(g for g in rep["gates"] if g["id"] == "R5_coverage")
    r6 = next(g for g in rep["gates"] if g["id"] == "R6_recon_clean")
    r7 = next(g for g in rep["gates"] if g["id"] == "R7_paper_sample")
    assert r5["pass"] is True
    assert r6["pass"] is True
    assert r7["pass"] is True
    assert rep["buyer_readiness_score"] >= 90


def test_build_institutional_payload(monkeypatch):
    monkeypatch.setattr(
        "hibs_predictor.racing_health_aggregator.fetch_upstream_racing_health",
        lambda full=True: (
            200,
            {
                "snapshot_coverage_pct": 60.0,
                "paper": {"n_rows": 30},
                "runners_loaded": 10,
                "scores_loaded": 10,
                "unscored_runners": 0,
                "nan_integrity_passed": True,
                "db_ui_in_sync": True,
            },
        ),
    )
    payload = build_institutional_racing_health()
    assert payload["inst_pp_layer"] == "institutional_plus_plus_racing"
    assert payload["sources"]["integration"] == "http_only"
    assert payload["telemetry_balance"]["coverage_pct"] == 60.0
    assert payload["paper"]["n_rows"] == 30
