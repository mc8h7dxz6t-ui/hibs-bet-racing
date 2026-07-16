"""Runner disarm registry tests."""

from __future__ import annotations

from hibs_racing.trading.runner_disarm_registry import disarm_runner, is_disarmed


def test_disarm_runner_blocks_routing():
    disarm_runner("R1:h1", reason="test")
    assert is_disarmed("R1:h1") is True
    assert is_disarmed("R1:h2") is False
