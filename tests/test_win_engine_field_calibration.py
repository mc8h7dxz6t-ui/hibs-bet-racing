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


def test_henery_exponential_second_place_reference_tolerance():
    from hibs_racing.place.hpl_combinatorial import institutional_reference_second_place

    probs = [0.5, 0.3, 0.2]
    gamma = 0.88
    got = institutional_reference_second_place(probs, runner_idx=1, gamma=gamma)
    g = [p**gamma for p in probs]
    total_g = sum(g)
    expected = (probs[0] * (g[1] / (total_g - g[0]))) + (probs[2] * (g[1] / (total_g - g[2])))
    assert got == pytest.approx(expected, abs=1e-5)


def test_place_liquidity_floor_mutes_execution_signals():
    import pandas as pd

    from hibs_racing.place.hpl_combinatorial import apply_place_alpha_and_liquidity

    frame = pd.DataFrame(
        [
            {
                "runner_id": "R1:a",
                "model_place_prob": 0.42,
                "offered_place_decimal": 2.5,
                "matchbook_place_liquidity": 1200.0,
                "value_flag": 1,
            }
        ]
    )
    out = apply_place_alpha_and_liquidity(frame)
    assert int(out.loc[0, "place_execution_muted"]) == 1
    assert int(out.loc[0, "value_flag"]) == 0
    assert out.loc[0, "value_gate_reason"] == "place_liquidity_floor"
    assert out.loc[0, "place_alpha_target"] is None


def test_place_alpha_target_emitted_above_edge_threshold():
    import pandas as pd

    from hibs_racing.place.hpl_combinatorial import apply_place_alpha_and_liquidity

    frame = pd.DataFrame(
        [
            {
                "runner_id": "R2:b",
                "model_place_prob": 0.50,
                "offered_place_decimal": 2.2,
                "matchbook_place_liquidity": 5000.0,
                "value_flag": 0,
            }
        ]
    )
    out = apply_place_alpha_and_liquidity(frame)
    assert out.loc[0, "place_alpha_target"] is not None
    assert "PLACE_ALPHA_TARGET" in str(out.loc[0, "place_alpha_target"])
    assert int(out.loc[0, "place_value_chip_active"]) == 1


def test_place_picker_config_tuple_sanitization(monkeypatch):
    from hibs_racing.place.place_picker_config import (
        liquidity_floor_gbp,
        min_place_edge_bps,
        place_henery_gamma_base,
    )

    monkeypatch.setenv("HIBS_PLACE_HENERY_GAMMA_BASE", "(0.91,)")
    monkeypatch.setenv("HIBS_PLACE_PICKER_MIN_EDGE_BPS", "(300,)")
    monkeypatch.setenv("HIBS_PLACE_LIQUIDITY_FLOOR_GBP", "(1750.5,)")
    assert place_henery_gamma_base() == pytest.approx(0.91, abs=1e-9)
    assert min_place_edge_bps() == 300
    assert liquidity_floor_gbp() == pytest.approx(1750.5, abs=1e-9)
