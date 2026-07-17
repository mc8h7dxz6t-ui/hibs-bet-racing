"""Variable field-size multiclass Brier calibration contract tests."""

from __future__ import annotations

import math

import pytest

from hibs_racing.features.store import connect, init_db
from hibs_racing.models.win_engine_circuit import (
    apply_calibration_circuit_breaker,
    devig_exchange_probabilities,
    evaluate_race_field_block,
    multiclass_field_brier,
    update_brier_on_result,
)
from hibs_racing.models.win_engine_config import max_brier_for_field_size
from hibs_racing.models.win_engine_store import ensure_win_engine_schema


def test_multiclass_field_brier_uniform_four_runner_field():
    probs = [0.25, 0.25, 0.25, 0.25]
    outcomes = [1, 0, 0, 0]
    assert multiclass_field_brier(probs, outcomes) == pytest.approx(0.75, abs=1e-9)


def test_max_brier_sliding_scale_mid_field():
    assert max_brier_for_field_size(6) == pytest.approx(0.280, abs=1e-9)
    assert max_brier_for_field_size(11) == pytest.approx(0.075, abs=1e-9)
    assert max_brier_for_field_size(12) == pytest.approx(0.075, abs=1e-9)
    assert max_brier_for_field_size(8) == pytest.approx(0.280 - 2 * 0.041, abs=1e-9)


def test_devig_exchange_probabilities_sum_to_one():
    odds = [3.0, 5.0, 8.0, 12.0]
    devig = devig_exchange_probabilities(odds)
    assert devig is not None
    assert sum(devig) == pytest.approx(1.0, abs=1e-6)
    assert all(p > 0 for p in devig)


def test_evaluate_race_field_block_market_beat():
    runners = [
        {
            "race_id": "R1",
            "true_probability": 0.70,
            "matchbook_back_odds": 2.0,
            "won": 1,
        },
        {
            "race_id": "R1",
            "true_probability": 0.30,
            "matchbook_back_odds": 4.0,
            "won": 0,
        },
    ]
    out = evaluate_race_field_block(runners, min_beat_bps=0)
    assert out["valid"] is True
    assert out["model_brier"] < out["market_brier"]
    assert out["block_pass"] is True


def _insert_settled_race(
    conn,
    *,
    race_id: str,
    model_probs: list[float],
    odds: list[float],
    winner_idx: int,
    ts: str,
) -> None:
    for i, (prob, odd) in enumerate(zip(model_probs, odds)):
        won = 1.0 if i == winner_idx else 0.0
        brier = (prob - won) ** 2
        conn.execute(
            """
            INSERT INTO win_engine_predictions (
                runner_id, race_id, true_probability, fair_odds, brier_score,
                live_odds_decimal, matchbook_back_odds, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"{race_id}:h{i}",
                race_id,
                prob,
                1.0 / prob if prob > 0 else 99.0,
                brier,
                odd,
                odd,
                ts,
            ),
        )
        field_brier = multiclass_field_brier(model_probs, [1 if j == winner_idx else 0 for j in range(len(model_probs))])
        devig = devig_exchange_probabilities(odds)
        market_brier = (
            multiclass_field_brier(devig, [1 if j == winner_idx else 0 for j in range(len(model_probs))])
            if devig
            else None
        )
        conn.execute(
            """
            UPDATE win_engine_predictions
            SET race_field_brier = ?, market_race_brier = ?, field_size = ?
            WHERE runner_id = ?
            """,
            (field_brier, market_brier, len(model_probs), f"{race_id}:h{i}"),
        )


def test_circuit_breaker_requires_five_hundred_races(tmp_path, monkeypatch):
    monkeypatch.setenv("HIBS_RACING_MIN_WIN_CALIBRATION_N", "500")
    db = tmp_path / "feature_store.sqlite"
    init_db(db)
    ensure_win_engine_schema(db)

    with connect(db) as conn:
        _insert_settled_race(
            conn,
            race_id="R1",
            model_probs=[0.6, 0.4],
            odds=[2.0, 4.0],
            winner_idx=0,
            ts="2026-05-01T12:00:00+00:00",
        )

    out = apply_calibration_circuit_breaker(db)
    assert out["calibration_state"] == "UNCALIBRATED"
    assert out["sample_n"] < 500
    assert out["action"] == "API_CLOAK_ENFORCED"


def test_circuit_breaker_trips_on_bounds_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("HIBS_RACING_MIN_WIN_CALIBRATION_N", "2")
    monkeypatch.setenv("HIBS_RACING_MIN_MARKET_BEAT_BPS", "0")
    db = tmp_path / "feature_store.sqlite"
    init_db(db)
    ensure_win_engine_schema(db)

    with connect(db) as conn:
        for idx in range(2):
            _insert_settled_race(
                conn,
                race_id=f"R{idx}",
                model_probs=[0.01, 0.99],
                odds=[2.0, 4.0],
                winner_idx=0,
                ts=f"2026-05-0{idx + 1}T12:00:00+00:00",
            )

    out = apply_calibration_circuit_breaker(db)
    assert out["calibration_state"] == "UNCALIBRATED"
    assert out["variable_bounds_check"] == "FAILED"


def test_update_brier_on_result_persists_race_field_brier(tmp_path):
    db = tmp_path / "feature_store.sqlite"
    init_db(db)
    ensure_win_engine_schema(db)

    with connect(db) as conn:
        conn.execute(
            """
            INSERT INTO win_engine_predictions (
                runner_id, race_id, true_probability, fair_odds, matchbook_back_odds, timestamp
            ) VALUES ('R1:a', 'R1', 0.6, 1.67, 2.0, datetime('now'))
            """
        )
        conn.execute(
            """
            INSERT INTO win_engine_predictions (
                runner_id, race_id, true_probability, fair_odds, matchbook_back_odds, timestamp
            ) VALUES ('R1:b', 'R1', 0.4, 2.5, 4.0, datetime('now'))
            """
        )
        update_brier_on_result(conn, race_id="R1", outcomes={"R1:a": 1, "R1:b": 2})
        row = conn.execute(
            "SELECT race_field_brier, market_race_brier, field_size FROM win_engine_predictions WHERE race_id='R1'"
        ).fetchone()
    assert row["race_field_brier"] is not None
    assert row["field_size"] == 2
    assert row["market_race_brier"] is not None
    assert math.isfinite(float(row["race_field_brier"]))


# --- Forensic gate alignment validations (liquidity routing telemetry) ---


def _strong_runner_telemetry() -> dict:
    return {
        "runner_id": "r-strong",
        "race_id": "race-1",
        "card_date": "2026-06-01",
        "course": "Ascot",
        "race_name": "Class 4 Handicap",
        "official_rating": 68,
        "trainer_rtf": 22.0,
        "field_size": 10,
        "win_decimal": 6.0,
        "place_ev": 0.10,
        "combo_bayes_place": 0.30,
        "model_place_prob": 0.40,
        "ew_combined_ev": 0.12,
        "stake": 10.0,
    }


def _weak_runner_telemetry() -> dict:
    return {
        "runner_id": "r-weak",
        "race_name": "Class 6 Handicap",
        "official_rating": 40,
        "trainer_rtf": 5.0,
        "field_size": 12,
        "win_decimal": 15.0,
        "place_ev": 0.01,
        "combo_bayes_place": 0.12,
        "model_place_prob": 0.10,
        "stake": 10.0,
    }


def test_gate_alignment_matrix_encodes_three_standards():
    from hibs_racing.gate_alignment_matrix import GateAlignmentMatrix

    matrix = GateAlignmentMatrix()
    assert len(matrix.INDUSTRY_STANDARDS) == 3
    assert len(matrix.ALIGNED_OVERLAYS) == 3
    assert len(matrix.FORENSIC_BLENDS) == 2


def test_evaluate_runner_against_blends_pass_strong_runner():
    from hibs_racing.gate_alignment_matrix import GateAlignmentMatrix, PASS_TRACE

    report = GateAlignmentMatrix().evaluate_runner_against_blends(_strong_runner_telemetry())
    assert report.verdict == "PASS"
    assert report.allocated_cap > 0.0
    assert report.order_trace == PASS_TRACE
    assert report.blend_id is not None or report.aligned_overlay is not None


def test_evaluate_runner_against_blends_reject_weak_runner():
    from hibs_racing.gate_alignment_matrix import DISARMED_TRACE, GateAlignmentMatrix

    report = GateAlignmentMatrix().evaluate_runner_against_blends(_weak_runner_telemetry())
    assert report.verdict == "REJECT"
    assert report.allocated_cap == 0.0
    assert report.order_trace == DISARMED_TRACE


def test_evaluate_runner_array_any_reject_disarms_batch():
    from hibs_racing.gate_alignment_matrix import GateAlignmentMatrix

    report = GateAlignmentMatrix().evaluate_runner_against_blends(
        [_strong_runner_telemetry(), _weak_runner_telemetry()]
    )
    assert report.verdict == "REJECT"


def test_telemetry_actionable_requires_ev_fields():
    from hibs_racing.gate_alignment_matrix import telemetry_actionable

    assert telemetry_actionable(_strong_runner_telemetry()) is True
    assert telemetry_actionable({"runner_id": "x", "odds": 5.0}) is False
