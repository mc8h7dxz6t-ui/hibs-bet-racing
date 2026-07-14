"""Tests for in-play evidence proxy (hibs-bet → FVE)."""

from __future__ import annotations


def test_inplay_evidence_from_fve_payload(monkeypatch):
    from hibs_predictor import inplay_evidence as ie

    payload = {
        "vertical": "inplay",
        "since_deploy_iso": "2026-06-01T00:00:00+00:00",
        "gates": [
            {"id": "I1_feed", "pass": True, "critical": True},
            {"id": "I2_model", "pass": True, "critical": False},
            {"id": "I3_marks", "pass": True, "critical": False},
            {"id": "I4_clv", "pass": True, "critical": False},
            {"id": "I5_paper", "pass": True, "critical": False},
        ],
        "critical_pass": True,
        "evidence_pass": True,
        "evidence_grade": "A",
        "buyer_ready": True,
        "buyer_readiness_score": 100.0,
    }

    out = ie.inplay_evidence_gates_from_payload(
        payload,
        base_url="http://127.0.0.1:8010",
        probes={"evidence": {"status": 200}},
        evidence_ok=True,
    )
    assert out["buyer_ready"] is True
    assert out["evidence_grade"] == "A"
    assert len(out["gates"]) == 5


def test_inplay_evidence_unreachable(monkeypatch):
    from hibs_predictor import inplay_evidence as ie

    def fake_get(url, *, timeout=None):
        return 0, "connection refused"

    monkeypatch.setattr(ie, "_http_get", fake_get)
    monkeypatch.setenv("FVE_API_URL", "http://127.0.0.1:8010")
    out = ie.inplay_evidence_gates()
    assert out["buyer_ready"] is False
    assert out["evidence_grade"] == "D"
    assert out["gates"][0]["id"] == "I0_fve"


def test_inplay_evidence_live_probe(monkeypatch):
    from hibs_predictor import inplay_evidence as ie

    def fake_get(url, *, timeout=None):
        if url.endswith("/api/inplay/evidence"):
            return 200, (
                '{"gates":[{"id":"I1_feed","pass":false,"critical":true}],'
                '"critical_pass":false,"evidence_pass":false,"evidence_grade":"D"}'
            )
        return 200, '{"status":"ok","inplay_evidence":{"buyer_ready":false}}'

    monkeypatch.setattr(ie, "_http_get", fake_get)
    out = ie.inplay_evidence_gates()
    assert out["buyer_ready"] is False
    assert out["gates"][0]["id"] == "I1_feed"
