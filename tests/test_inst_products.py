"""Product packages — compliance_log, proxy_risk, altdata, ai_kit."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from altdata.poll import poll_once
from altdata.structural_rescue import structural_rescue
from ai_kit.pipeline import AgentLoop
from compliance_log.ingest import log_decision
from inst_spine.check import run_institutional_check
from inst_spine.ledger import AppendOnlyLedger
from proxy_risk.router import ProxyRequest, ProxyRiskGateway


def test_compliance_log_chain(tmp_path: Path):
    db = tmp_path / "compliance.sqlite"
    log_decision(
        snapshot={"input": "approve loan"},
        outcome={"decision": "approved"},
        actor="auditor",
        database=db,
    )
    ledger = AppendOnlyLedger(db, writer_id="auditor")
    assert ledger.verify()["chain_ok"]


def test_compliance_clock_attack_chain_still_valid(tmp_path: Path):
    """F4 uses Lamport — wall clock manipulation must not break chain."""
    db = tmp_path / "attack.sqlite"
    ledger = AppendOnlyLedger(db, writer_id="w")
    ledger.append(event_type="e", payload={"n": 1}, manifest_id="m")
    entries = ledger.list_entries()
    entries[0]["wall_time_utc"] = "1999-01-01T00:00:00+00:00"
    from inst_spine.hash import verify_chain

    assert verify_chain(entries).ok


@pytest.mark.asyncio
async def test_proxy_risk_token_bucket_blocks_burst(tmp_path: Path):
    db = tmp_path / "proxy.sqlite"
    ledger = AppendOnlyLedger(db, async_writes=True)
    ledger.start_async_writer()
    from inst_spine.rates import TokenBucket

    gw = ProxyRiskGateway(
        ledger=ledger,
        bucket=TokenBucket(capacity=2.0, refill_rate=0.01),
        shadow_mode=True,
    )
    req = ProxyRequest(client_id="c1", method="POST", path="/o", body={})
    r1 = await gw.evaluate(req)
    r2 = await gw.evaluate(ProxyRequest(client_id="c2", method="POST", path="/o2", body={}))
    r3 = await gw.evaluate(ProxyRequest(client_id="c3", method="POST", path="/o3", body={}))
    assert r1.decision.value == "approve"
    assert r2.decision.value == "approve"
    assert r3.decision.value == "reject"
    ledger.stop_async_writer(flush=True)


@pytest.mark.asyncio
async def test_proxy_risk_zscore_kill():
    from inst_spine.rates import ZScoreDriftDetector

    drift = ZScoreDriftDetector(window=5, z_max=2.0)
    for p in [10.0, 10.1, 9.9, 10.0, 10.2]:
        drift.update(p)
    gw = ProxyRiskGateway(drift=drift, shadow_mode=True)
    resp = await gw.evaluate(
        ProxyRequest(client_id="c", method="POST", path="/x", body={}, reference_price=50.0)
    )
    assert resp.decision.value == "kill"


def test_altdata_structural_rescue():
    html = '<div data-price="199.50">fare</div>'
    assert structural_rescue(html, "fare_price") == 199.5


def test_altdata_poll_coverage(tmp_path: Path):
    db = tmp_path / "alt.sqlite"
    result = poll_once(
        feed_id="demo",
        ctx={"demo_price": 120.0, "demo_seats": 4, "demo_route": "LHR-JFK"},
        database=db,
    )
    assert result.ok
    assert result.coverage_pct == 100.0
    ledger = AppendOnlyLedger(db, writer_id="demo")
    assert ledger.verify()["chain_ok"]


def test_altdata_rescue_rung(tmp_path: Path):
    db = tmp_path / "rescue.sqlite"
    html = '{"price": 88.5}'
    result = poll_once(
        feed_id="rescue",
        ctx={"raw_html": html},
        database=db,
    )
    assert result.record["fare_price"] == 88.5
    assert "fare_price" in (result.record.get("_meta") or {}).get("rescue_fields", [])


def test_ai_kit_checkpoint_resume(tmp_path: Path):
    cp_db = tmp_path / "cp.sqlite"
    loop = AgentLoop(agent_id="t", checkpoint_db=cp_db)

    def step_fn(step: int, state: dict) -> dict:
        state = dict(state)
        state["count"] = state.get("count", 0) + 1
        return state

    loop.run_steps(start_step=0, steps=2, step_fn=step_fn)
    loop2 = AgentLoop(agent_id="t", checkpoint_db=cp_db)
    final = loop2.run_steps(start_step=0, steps=2, step_fn=step_fn)
    assert final["count"] == 4


def test_institutional_check_passes_clean_ledger(tmp_path: Path):
    db = tmp_path / "inst.sqlite"
    ledger = AppendOnlyLedger(db)
    ledger.append(event_type="x", payload={"a": 1}, manifest_id="m")
    report = run_institutional_check(
        ledger=ledger,
        context={
            "ledger_entries": ledger.list_entries(),
            "expected_count": 1,
            "actual_count": 1,
            "source_coverage_pct": 100.0,
        },
    )
    assert report.passed
