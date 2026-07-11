"""Ingress schema guard, OddsPapi mapping, Brier FSM, CSV baseline."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hibs_predictor.ingress.football_data_csv_baseline import parse_football_data_csv
from hibs_predictor.ingress.price_truth_ingress import oddspapi_event_to_bookmaker_panel
from hibs_predictor.ingress.schema_guard import IngressRejectError, validate_ingress_payload
from hibs_predictor.safety.brier_circuit_breaker import (
    BreakerState,
    BrierCircuitBreaker,
    execution_lockout_active,
    persist_breaker_state,
)


def test_schema_guard_rejects_missing_version():
    with pytest.raises(IngressRejectError):
        validate_ingress_payload({}, expected_min="1.0.0")


def test_schema_guard_accepts_semver_range():
    v = validate_ingress_payload(
        {"schema_version": "1.2.0", "event_id": "e1"},
        expected_min="1.0.0",
        expected_max="1.99.99",
        required_paths=("event_id",),
    )
    assert v == "1.2.0"


def test_oddspapi_panel_maps_sharp_books():
    event = {
        "schema_version": "1.0.0",
        "event_id": "abc",
        "bookmakers": [
            {
                "name": "pinnacle",
                "markets": [
                    {
                        "key": "h2h",
                        "outcomes": [
                            {"name": "Home", "price": 2.1},
                            {"name": "Draw", "price": 3.4},
                            {"name": "Away", "price": 3.8},
                        ],
                    }
                ],
            }
        ],
    }
    panel = oddspapi_event_to_bookmaker_panel(event)
    assert panel[0]["bookmaker"] == "Pinnacle"
    assert panel[0]["home"] == 2.1


def test_brier_fsm_trips_open_then_half_open(monkeypatch):
    br = BrierCircuitBreaker(threshold=0.25, min_samples=5, cooldown_sec=0.0, half_open_samples=2)
    assert br.evaluate(0.30, 25, now=0.0) == BreakerState.OPEN
    assert not br.allows_execution()[0]
    assert br.evaluate(0.20, 25, now=1.0) == BreakerState.HALF_OPEN
    assert br.evaluate(0.20, 25, now=2.0) == BreakerState.HALF_OPEN
    assert br.evaluate(0.20, 25, now=3.0) == BreakerState.CLOSED
    assert br.allows_execution()[0]


def test_execution_lockout_reads_state_file(tmp_path, monkeypatch):
    monkeypatch.delenv("HIBS_EXECUTION_LOCKOUT", raising=False)
    state = tmp_path / "brier_circuit_state.json"
    monkeypatch.setenv("HIBS_BRIER_STATE_PATH", str(state))
    br = BrierCircuitBreaker(state=BreakerState.OPEN, reason="test")
    persist_breaker_state(br, path=state)
    assert execution_lockout_active()


def test_football_data_csv_parser(tmp_path):
    csv_path = tmp_path / "E0.csv"
    csv_path.write_text(
        "Div,Date,HomeTeam,AwayTeam,FTR,B365H,B365D,B365A\n"
        "E0,01/08/2024,Arsenal,Chelsea,H,2.1,3.4,3.8\n",
        encoding="utf-8",
    )
    rows = list(parse_football_data_csv(csv_path))
    assert rows[0].home_team == "Arsenal"
    seed = rows[0].to_price_truth_seed()
    assert seed["price_truth"]["baseline_source"] == "football_data_co_uk_csv"
