import pandas as pd
import pytest

from hibs_racing.analytics.gate_audit import (
    audit_gate_data_deprivation,
    audit_gate_lane,
    feature_coverage_table,
)


def _sample_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "runner_id": "r1",
                "official_rating": 70,
                "trainer_rtf": 18.0,
                "win_decimal": 5.0,
                "place_ev": 0.08,
                "combo_bayes_place": 0.3,
                "model_place_prob": 0.4,
                "horse_distance_runs": 5,
                "horse_distance_wins": 1,
                "form_trip_change_f": 0.0,
                "form_poor_runs_3": 0,
                "enrich_source": "rpscrape_racecards",
            },
            {
                "runner_id": "r2",
                "official_rating": 65,
                "trainer_rtf": None,
                "win_decimal": 8.0,
                "place_ev": 0.06,
                "combo_bayes_place": 0.25,
                "model_place_prob": 0.35,
                "horse_distance_runs": None,
                "horse_distance_wins": None,
                "form_trip_change_f": None,
                "form_poor_runs_3": None,
                "enrich_source": None,
            },
            {
                "runner_id": "r3",
                "official_rating": 80,
                "trainer_rtf": 8.0,
                "win_decimal": 3.5,
                "place_ev": 0.1,
                "combo_bayes_place": 0.35,
                "model_place_prob": 0.5,
                "horse_distance_runs": 4,
                "horse_distance_wins": 0,
                "form_trip_change_f": 1.0,
                "form_poor_runs_3": 2,
                "enrich_source": "raceform_derived",
            },
        ]
    )


def test_feature_coverage_null_only_not_zero_counter():
    frame = _sample_frame()
    rows = feature_coverage_table(frame, ("form_poor_runs_3", "trainer_rtf"))
    by_col = {r.column: r for r in rows}
    assert by_col["form_poor_runs_3"].present_pct == pytest.approx(66.67, abs=0.1)
    assert by_col["trainer_rtf"].present_pct == pytest.approx(66.67, abs=0.1)


def test_gate7_high_hindrance_on_sparse_rtf():
    frame = _sample_frame()
    audit = audit_gate_lane(frame, "gate7", min_density_pct=85.0)
    assert audit.verdict == "partial_hindrance"
    assert audit.data_density_pct == pytest.approx(66.67, abs=0.1)
    assert audit.cold_trainer_skipped_null_rtf == 1
    assert audit.cold_trainer_would_block == 2  # r1 RTF 18, r3 RTF 8 — both below gate7 floor 20
    assert audit.min_trainer_rtf == 20.0


def test_gate3_partial_with_mixed_coverage():
    frame = _sample_frame()
    audit = audit_gate_lane(frame, "gate3", min_density_pct=85.0)
    assert audit.data_density_pct < 85.0
    assert audit.trainer_rtf_present_pct == pytest.approx(66.67, abs=0.1)
    assert any("NULL trainer_rtf" in n for n in audit.notes)


def test_audit_gate_data_deprivation_wrapper():
    frame = _sample_frame()
    audit = audit_gate_data_deprivation(frame, "gate5")
    assert audit.lane == "gate5"
    assert audit.min_trainer_rtf == 15.0

