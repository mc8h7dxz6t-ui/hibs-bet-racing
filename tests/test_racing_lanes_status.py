"""Tests for racing lane status panel context."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from hibs_racing.racing_lanes_status import build_racing_lanes_status


def test_build_racing_lanes_status_tier_counts_match_audit():
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
        gate_tier_counts={
            "watchlist": 40,
            "value": 12,
            "value_lane": 5,
            "paper_ready": 3,
            "sniper": 0,
            "none": 55,
        },
    )
    assert out["value_lane_count"] == 5
    assert out["value_lane_display_count"] == 1
    assert out["sniper_lane_count"] == 0
    assert out["watchlist_count"] == 40
    assert out["paper_ready_count"] == 3
    assert out["place_engine_count"] == 43
    assert out["place_engine_display_count"] == 2
    assert out["raw_value_count"] == 3
    assert any("sniper" in h.lower() for h in out["hints"])


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
    assert any("Matchbook" in h for h in out["hints"])
    assert any("Racing API" in h for h in out["hints"])


def test_build_racing_lanes_status_gate_blocks():
    health = SimpleNamespace(
        value_lane_ready=True,
        value_lane_blockers=[],
        matchbook=True,
        racing_api=True,
        production_value_count=0,
    )
    out = build_racing_lanes_status(
        health=health,
        value_lane_picks=[],
        sniper_lane_picks=[],
        value_count=10,
        runner_count=100,
        gate_blocks=[("thin_odds", 42), ("low_dq", 8)],
    )
    assert out["gate_blocks"] == [
        {"reason": "thin_odds", "count": 42},
        {"reason": "low_dq", "count": 8},
    ]


def test_win_engine_staging_status_note(monkeypatch):
    monkeypatch.setenv("HIBS_WIN_ENGINE_CONFIGURED", "1")
    monkeypatch.setenv("HIBS_WIN_ENGINE_ACTIVE", "false")
    monkeypatch.setenv("HIBS_RACING_MIN_WIN_CALIBRATION_N", "100")

    health = SimpleNamespace(
        value_lane_ready=True,
        value_lane_blockers=[],
        matchbook=True,
        racing_api=True,
        production_value_count=0,
    )
    out = build_racing_lanes_status(
        health=health,
        value_lane_picks=[],
        sniper_lane_picks=[],
        value_count=0,
        runner_count=10,
    )
    win = out["win_engine"]
    assert win["staging_configured"] is True
    assert win["env_requested"] is False
    assert "staging" in win["status_note"].lower()
    assert any("staging" in h.lower() for h in out["hints"])
