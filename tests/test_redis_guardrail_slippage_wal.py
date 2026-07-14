"""Redis guardrail memory fallback, slippage guard, webhook WAL."""

from __future__ import annotations

from pathlib import Path

from hibs_racing.execution.slippage_guard import ExecutionState, evaluate_fill_slippage
from hibs_racing.redis_guardrail_client import RedisGuardrailClient
from inst_spine.webhook_wal import WebhookWal, capture_before_parse


def test_redis_guardrail_memory_steam():
    client = RedisGuardrailClient(redis_url="")
    r1 = client.record_odds("R1:h1", feed="matchbook", odds=5.0, steam_threshold_pct=8.0)
    assert r1["direction"] == "unknown"
    r2 = client.record_odds("R1:h1", feed="matchbook", odds=4.0, steam_threshold_pct=8.0)
    assert r2["direction"] == "steam"
    assert r2["gate"] == "scale_up"


def test_slippage_guard_holds_on_ev_burn():
    verdict = evaluate_fill_slippage(
        requested_odds=4.0,
        filled_odds=3.2,
        model_prob=0.30,
        max_ev_burn_pct=1.5,
    )
    assert not verdict.allowed
    assert verdict.state == ExecutionState.HELD


def test_slippage_guard_allows_tight_fill():
    verdict = evaluate_fill_slippage(
        requested_odds=4.0,
        filled_odds=3.99,
        model_prob=0.30,
        max_ev_burn_pct=1.5,
    )
    assert verdict.allowed
    assert verdict.state == ExecutionState.FILLED


def test_webhook_wal_roundtrip(tmp_path):
    root = tmp_path / "wal"
    payload = b'{"events":[]}'
    path = capture_before_parse("test", payload, root=root, source="unit")
    assert path.suffix == ".wrcap"
    seq, raw = WebhookWal.read_record(path)
    assert seq == 0
    assert raw == payload
