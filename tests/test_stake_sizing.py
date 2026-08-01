"""Racing Kelly stake sizing tests."""

from __future__ import annotations

import pandas as pd

from hibs_racing.place.stake_sizing import resolve_stake_units


def test_resolve_stake_from_kelly_pct():
    row = {"kelly_place_pct": 2.5}
    assert resolve_stake_units(row, bankroll_units=100.0, default_stake=1.0) == 2.5


def test_resolve_stake_each_way_uses_ew_kelly():
    row = {"kelly_ew_pct": 2.0, "kelly_place_pct": 1.0}
    assert resolve_stake_units(row, bankroll_units=100.0, bet_type="each_way") == 2.0


def test_resolve_stake_fallback_without_kelly():
    row = {"kelly_place_pct": None}
    assert resolve_stake_units(row, default_stake=1.0) == 1.0


def test_resolve_stake_steam_multiplier():
    row = {"kelly_place_pct": 2.0}
    assert resolve_stake_units(row, bankroll_units=100.0, kelly_multiplier=1.25) == 2.5


def test_build_execution_intents_uses_kelly(monkeypatch):
    from hibs_racing.live.execution_router import build_execution_intents

    monkeypatch.setattr(
        "hibs_racing.live.execution_router.execution_disabled",
        lambda: False,
    )
    monkeypatch.setattr(
        "hibs_racing.live.execution_router.evaluate_market_gauges",
        lambda: [],
    )
    scored = pd.DataFrame(
        [
            {
                "runner_id": "r1",
                "race_id": "race1",
                "horse_name": "Star",
                "value_flag": 1,
                "win_decimal": 5.0,
                "kelly_place_pct": 1.5,
            }
        ]
    )
    intents = build_execution_intents(scored, default_stake=1.0)
    assert len(intents) == 1
    assert intents[0].stake == 1.5
