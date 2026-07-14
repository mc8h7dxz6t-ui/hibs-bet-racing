"""Tests for cache preservation and personal staking gates."""

from __future__ import annotations


def test_bundle_quality_score_prefers_odds_and_dq():
    from hibs_predictor.cache_preservation_policy import bundle_quality_score

    thin = {"all": [{"data_quality": {"score_pct": 40}}] * 5}
    rich = {
        "all": [
            {
                "data_quality": {"score_pct": 85, "full_scope": True},
                "best_odds_1x2": {"home": 2.1, "draw": 3.4, "away": 3.2},
            }
        ]
        * 5
    }
    assert bundle_quality_score(rich) > bundle_quality_score(thin)


def test_should_replace_requires_delta():
    from hibs_predictor.cache_preservation_policy import should_replace_bundle

    incumbent = {
        "all": [
            {
                "data_quality": {"score_pct": 80, "full_scope": True},
                "best_odds_1x2": {"home": 2.0},
            }
        ]
    }
    same = dict(incumbent)
    assert should_replace_bundle(incumbent, same) is False
    empty = {"all": []}
    assert should_replace_bundle(empty, incumbent) is True


def test_personal_staking_report_structure():
    from hibs_predictor.personal_staking_gates import personal_staking_report

    rep = personal_staking_report()
    assert rep.get("personal_project") is True
    assert "lanes" in rep
    assert "football" in rep["lanes"]
    assert "honesty" in rep


def test_f10_gate_present():
    from hibs_predictor.forward_evidence import forward_evidence_gates

    rep = forward_evidence_gates()
    ids = {g["id"] for g in rep.get("gates") or []}
    assert "F10_brier_1x2" in ids
