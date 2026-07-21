"""Tests for racing lane status panel context."""

from __future__ import annotations

from types import SimpleNamespace

from hibs_racing.racing_lanes_status import build_racing_lanes_status


def test_build_racing_lanes_status_counts_picks():
    health = SimpleNamespace(
        value_lane_ready=True,
        value_lane_blockers=[],
        matchbook=True,
        racing_api=True,
        production_value_count=2,
    )
    out = build_racing_lanes_status(
        health=health,
        value_lane_picks=[{"horse_name": "A"}],
        sniper_lane_picks=[],
        engine_top_picks=[{"horse_name": "B"}, {"horse_name": "C"}],
        value_count=3,
        runner_count=100,
    )
    assert out["value_lane_count"] == 1
    assert out["sniper_lane_count"] == 0
    assert out["place_engine_count"] == 2
    assert out["raw_value_count"] == 3
    assert any("Gate7" in h for h in out["hints"])


def test_build_racing_lanes_status_matchbook_hint():
    health = SimpleNamespace(
        value_lane_ready=False,
        value_lane_blockers=["unscored_runners=5"],
        matchbook=False,
        racing_api=False,
        production_value_count=0,
    )
    out = build_racing_lanes_status(
        health=health,
        value_lane_picks=[],
        sniper_lane_picks=[],
        value_count=0,
        runner_count=50,
    )
    assert out["value_lane_blockers"] == ["unscored_runners=5"]
    assert any("MATCHBOOK" in h for h in out["hints"])
    assert any("RACING_API" in h for h in out["hints"])
