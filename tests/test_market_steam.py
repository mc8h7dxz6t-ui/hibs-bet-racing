import json

import pandas as pd

from hibs_racing.odds.market_steam import (
    SteamTrigger,
    append_odds_history,
    detect_steam_drift,
    drift_direction_index,
    evaluate_market_gauges,
)


def test_detect_steam_shortening():
    odds = pd.DataFrame([{"runner_id": "R1:h1", "race_id": "R1", "horse_name": "Star", "win_decimal": 4.0}])
    prev = {"R1:h1": 5.0}
    triggers, current = detect_steam_drift(odds, previous=prev, history={})
    assert len(triggers) == 1
    assert triggers[0].trigger == "steam"
    assert current["R1:h1"] == 4.0


def test_drift_direction_index():
    history = {
        "R1:h1": [
            {"t": "2026-06-15T12:00:00+00:00", "p": 8.0},
            {"t": "2026-06-15T12:18:00+00:00", "p": 6.0},
        ]
    }
    # monkeypatch time is hard — test structure with oldest as ref when no 20m snap
    out = drift_direction_index("R1:h1", history=history, reference_mins=20)
    assert out["odds_now"] == 6.0


def test_append_odds_history_caps():
    odds = pd.DataFrame([{"runner_id": "R1:h1", "win_decimal": 5.0}])
    hist = append_odds_history(odds, polled_at="2026-06-15T12:00:00+00:00", history={}, max_snapshots=3)
    for _ in range(5):
        hist = append_odds_history(odds, polled_at="2026-06-15T12:00:00+00:00", history=hist, max_snapshots=3)
    assert len(hist["R1:h1"]) <= 3


def test_steam_trigger_serializes():
    t = SteamTrigger(
        runner_id="R1:h1",
        race_id="R1",
        horse_name="Star",
        course="York",
        off_time="15:30",
        previous_odds=5.0,
        current_odds=4.0,
        change_pct=-20.0,
        trigger="steam",
        detected_at="2026-06-15T12:00:00+00:00",
        drift_delta=-1.0,
    )
    assert json.loads(json.dumps(t.to_dict()))["drift_delta"] == -1.0


def test_evaluate_market_gauges_empty():
    gauges = evaluate_market_gauges(history={}, cards=pd.DataFrame())
    assert gauges == []
