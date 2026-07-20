"""Tests for neutral engine pick display + accuracy readout."""

from __future__ import annotations

from hibs_racing.daily.pick_display import (
    build_pick_accuracy,
    classify_display_pick,
    enrich_pick_display,
    passes_loose_pick,
    passes_strict_pick,
)


def test_passes_strict_requires_value_and_dq():
    pick = {
        "value_flag": True,
        "data_quality_pct": 96,
        "steam_gate": "proceed",
        "value_gate_reason": None,
    }
    assert passes_strict_pick(pick) is True
    pick["value_flag"] = False
    assert passes_strict_pick(pick) is False


def test_passes_loose_allows_lower_dq():
    pick = {
        "data_quality_pct": 62,
        "steam_gate": "scale_down",
    }
    assert passes_loose_pick(pick) is True
    pick["data_quality_pct"] = 50
    assert passes_loose_pick(pick) is False


def test_classify_display_tiers_neutral_labels():
    strict = {
        "value_flag": True,
        "data_quality_pct": 96,
        "steam_gate": "proceed",
        "value_gate_reason": None,
    }
    out = classify_display_pick(strict)
    assert out["display_tier"] == "paper_ready"
    assert out["display_tier_label"] == "Paper-ready"

    loose_only = {"data_quality_pct": 65, "steam_gate": "scale_down"}
    out2 = classify_display_pick(loose_only)
    assert out2["display_tier"] == "watchlist"

    engine = {"data_quality_pct": 40, "steam_gate": "abort"}
    out3 = classify_display_pick(engine)
    assert out3["display_tier"] == "engine_lead"
    assert out3["display_tier_label"] == "Engine lead"


def test_build_pick_accuracy_includes_probabilities():
    acc = build_pick_accuracy(
        {
            "display_rank": 1,
            "model_place_prob": 0.52,
            "combo_bayes_place": 0.41,
            "place_score": 0.48,
        },
        holdout={"place_auc": 0.68, "top1_hit_rate": 0.31},
    )
    assert acc["place_prob_pct"] == 52.0
    assert acc["combo_prob_pct"] == 41.0
    assert any("Blended place score" in line for line in acc["accuracy_lines"])
    assert any("place AUC" in line for line in acc["accuracy_lines"])


def test_enrich_pick_display_merges_reasons():
    out = enrich_pick_display(
        {
            "horse_name": "Test",
            "model_place_prob": 0.5,
            "combo_bayes_place": 0.4,
            "display_rank": 2,
            "pick_summary": "Strong combo prior.",
            "pick_reasons": ["Strong combo prior."],
            "data_quality_pct": 55,
            "steam_gate": "abort",
        },
        holdout={},
    )
    assert out["display_tier"] == "engine_lead"
    assert len(out.get("pick_reasons") or []) >= 2
    assert out.get("pick_accuracy")
