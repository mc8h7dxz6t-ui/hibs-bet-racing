"""Tests for racing DQ target helpers and reboost pipeline."""

from __future__ import annotations

import pandas as pd


def test_racing_dq_target_defaults_95(monkeypatch):
    monkeypatch.delenv("HIBS_RACING_TARGET_DQ_PCT", raising=False)
    monkeypatch.delenv("HIBS_RACING_ENRICH_RECOVERY_MIN_PCT", raising=False)
    monkeypatch.delenv("HIBS_ENGINE_OUTPUT_MIN_DQ_PCT", raising=False)
    from hibs_racing.data_quality_targets import (
        racing_data_quality_target_pct,
        racing_engine_output_min_dq_pct,
        racing_enrich_recovery_min_pct,
        racing_rescue_max_per_cycle,
    )

    assert racing_data_quality_target_pct() == 95.0
    assert racing_enrich_recovery_min_pct() == 95.0
    assert racing_engine_output_min_dq_pct() == 90.0
    assert racing_rescue_max_per_cycle() == 64


def test_run_data_quality_reboost_skips_when_at_target(monkeypatch):
    monkeypatch.setattr(
        "hibs_racing.scrapers.racing_scrape_api.load_scored_cards",
        lambda: pd.DataFrame(
            [
                {
                    "runner_id": "r1",
                    "race_name": "Handicap",
                    "win_decimal": 4.0,
                    "model_win_prob": 0.2,
                    "model_place_prob": 0.4,
                    "jockey": "A",
                    "trainer": "B",
                    "official_rating": 80,
                    "card_comment": "held up",
                    "enrich_source": "rp",
                    "form_string": "112",
                    "trainer_rtf": 20,
                    "horse_course_win_rate": 0.1,
                }
            ]
        ),
    )
    from hibs_racing.scrapers.racing_scrape_api import run_data_quality_reboost

    out = run_data_quality_reboost()
    assert out.get("skipped") is True
    assert out["mean_dq_before"] >= 95


def test_enrich_block_counts_trainer_rtf():
    from hibs_racing.cards.data_quality import runner_quality_blocks

    blocks = runner_quality_blocks(
        {
            "race_name": "Class 4 Handicap",
            "enrich_source": "rp",
            "form_string": "112",
            "trainer_rtf": 18,
            "horse_course_win_rate": 0.15,
        }
    )
    assert blocks["enrich"]["pct"] == 100
    blocks_thin = runner_quality_blocks(
        {
            "race_name": "Class 4 Handicap",
            "enrich_source": "rp",
            "form_string": "112",
        }
    )
    assert blocks_thin["enrich"]["pct"] < 100
    assert "trainer_rtf" in blocks_thin["enrich"]["missing"]
