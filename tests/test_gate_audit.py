import pandas as pd
import pytest

from hibs_racing.analytics.gate_audit import (
    audit_gate_data_deprivation,
    audit_gate_lane,
    feature_coverage_table,
    run_gate_coverage_audit,
)
from hibs_racing.backtest.snapshot_store import upsert_snapshots
from hibs_racing.features.store import connect, init_db


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


def test_gate_coverage_both_uses_snapshot_replay_as_retest_source(tmp_path):
    db = tmp_path / "audit.db"
    init_db(db)
    with connect(db) as conn:
        for idx in range(3):
            conn.execute(
                """
                INSERT INTO runners (
                    runner_id, race_id, horse_id, race_date, course, finish_pos,
                    sp_decimal, official_rating, trainer_rtf, ingested_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"r{idx}",
                    f"race{idx}",
                    f"horse{idx}",
                    "2026-06-01",
                    "Ascot",
                    idx + 1,
                    5.0,
                    None,
                    None,
                    "2026-06-02T00:00:00Z",
                ),
            )
    snap = pd.DataFrame(
        [
            {
                "runner_id": f"r{idx}",
                "race_id": f"race{idx}",
                "course": "Ascot",
                "race_name": "Handicap",
                "field_size": 10,
                "official_rating": 75,
                "win_decimal": 5.0,
                "place_fraction": 0.25,
                "places": 3,
                "model_score": 0.9,
                "model_win_prob": 0.2,
                "model_place_prob": 0.45,
                "combo_bayes_place": 0.3,
                "place_ev": 0.08,
                "ew_combined_ev": 0.1,
                "flag_raw": 1,
                "trainer_rtf": 22.0,
                "horse_course_win_rate": 0.2,
                "enrich_source": "snapshot_replay",
            }
            for idx in range(3)
        ]
    )
    upsert_snapshots(
        db,
        "2026-06-01",
        snap,
        finish_by_runner={f"r{idx}": idx + 1 for idx in range(3)},
    )

    report = run_gate_coverage_audit(
        start="2026-06-01",
        end="2026-06-01",
        lanes=("gate3", "gate5", "gate7"),
        database=db,
        source="both",
    )

    assert report["retest_source"] == "snapshots"
    assert report["retest_ready"] is True
    assert report["snapshot_retest_ready"] is True
    assert report["runners_retest_ready"] is False
    assert "non-blocking" in report["diagnostic_note"]


def test_gate_coverage_reports_domestic_and_international_universes(tmp_path):
    db = tmp_path / "audit_universe.db"
    init_db(db)
    with connect(db) as conn:
        for rid, course in (("r1", "Ascot"), ("r2", "Sha Tin")):
            conn.execute(
                """
                INSERT INTO runners (
                    runner_id, race_id, horse_id, race_date, course, finish_pos,
                    sp_decimal, official_rating, trainer_rtf, ingested_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rid,
                    f"race_{rid}",
                    f"horse_{rid}",
                    "2026-06-01",
                    course,
                    1,
                    5.0,
                    75,
                    20.0 if course == "Ascot" else None,
                    "2026-06-02T00:00:00Z",
                ),
            )
    snap = pd.DataFrame(
        [
            {
                "runner_id": "r1",
                "race_id": "race_r1",
                "course": "Ascot",
                "race_name": "Handicap",
                "field_size": 10,
                "official_rating": 75,
                "win_decimal": 5.0,
                "place_fraction": 0.25,
                "places": 3,
                "model_score": 0.9,
                "model_win_prob": 0.2,
                "model_place_prob": 0.45,
                "combo_bayes_place": 0.3,
                "place_ev": 0.08,
                "ew_combined_ev": 0.1,
                "flag_raw": 1,
                "trainer_rtf": 22.0,
                "horse_course_win_rate": 0.2,
            },
            {
                "runner_id": "r2",
                "race_id": "race_r2",
                "course": "Sha Tin",
                "race_name": "Handicap",
                "field_size": 10,
                "official_rating": 75,
                "win_decimal": 5.0,
                "place_fraction": 0.25,
                "places": 3,
                "model_score": 0.9,
                "model_win_prob": 0.2,
                "model_place_prob": 0.45,
                "combo_bayes_place": 0.3,
                "place_ev": 0.08,
                "ew_combined_ev": 0.1,
                "flag_raw": 1,
                "horse_course_win_rate": 0.2,
            },
        ]
    )
    upsert_snapshots(db, "2026-06-01", snap, finish_by_runner={"r1": 1, "r2": 1})

    report = run_gate_coverage_audit(
        start="2026-06-01",
        end="2026-06-01",
        lanes=("gate3", "gate5", "gate7"),
        database=db,
        source="snapshots",
    )
    universes = report["snapshots"]["coverage_universes"]

    assert report["coverage_universe"] == "domestic_gb_ire"
    assert report["retest_ready"] is True
    assert universes["all"]["retest_ready"] is False
    assert universes["domestic_gb_ire"]["retest_ready"] is True
    assert universes["international"]["retest_ready"] is False
    assert universes["domestic_gb_ire"]["runners"] == 1
    assert universes["international"]["runners"] == 1
