"""Ad Guard — spend parsers, gate chain, institutional positioning."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ad_guard.proxy import AdGuardGateway, AdSpendRequest
from ad_guard.spend import extract_spend_metrics
from inst_spine.ledger import AppendOnlyLedger
from inst_spine.rates import MemoryTokenBucketBackend, TokenBucket, ZScoreDriftDetector


def test_extract_google_campaign_and_micros():
    body = {
        "campaignId": "12345",
        "bidMicros": 2_500_000,
        "costMicros": 10_000_000,
    }
    cid, bid, spend = extract_spend_metrics(body, provider="google")
    assert cid == "12345"
    assert bid == 2.5
    assert spend == 10.0


def test_extract_google_resource_name():
    body = {"resourceName": "customers/1/campaigns/999", "bidMicros": 1_000_000}
    cid, bid, _ = extract_spend_metrics(body, provider="google")
    assert cid == "999"
    assert bid == 1.0


def test_extract_meta_campaign():
    body = {"campaign_id": "meta-77", "daily_budget": 500.0, "spend": 120.0}
    cid, bid, spend = extract_spend_metrics(body, provider="meta")
    assert cid == "meta-77"
    assert bid == 500.0
    assert spend == 120.0


@pytest.mark.asyncio
async def test_ad_guard_campaign_bucket_blocks_burst():
    backend = MemoryTokenBucketBackend()
    gw = AdGuardGateway(
        bucket_capacity=2.0,
        bucket_refill=0.01,
        rate_backend=backend,
        shadow_mode=True,
    )
    req = AdSpendRequest(
        client_id="agency",
        method="POST",
        path="/mutate",
        body={"campaign_id": "c1", "bid_amount": 1.0},
    )
    r1 = await gw.evaluate(req)
    r2 = await gw.evaluate(AdSpendRequest(
        client_id="agency", method="POST", path="/mutate2",
        body={"campaign_id": "c1", "bid_amount": 1.0},
    ))
    r3 = await gw.evaluate(AdSpendRequest(
        client_id="agency", method="POST", path="/mutate3",
        body={"campaign_id": "c1", "bid_amount": 1.0},
    ))
    assert r1.decision.value == "approve"
    assert r2.decision.value == "approve"
    assert r3.decision.value == "reject"


@pytest.mark.asyncio
async def test_ad_guard_spend_zscore_kill():
    drift = ZScoreDriftDetector(window=5, z_max=2.0)
    for p in [10.0, 10.1, 9.9, 10.0, 10.2]:
        drift.update(p)
    gw = AdGuardGateway(shadow_mode=True)
    gw._drift_by_campaign["c1"] = drift
    resp = await gw.evaluate(AdSpendRequest(
        client_id="agency",
        method="POST",
        path="/mutate",
        body={"campaign_id": "c1", "spend_delta": 500.0},
        campaign_id="c1",
    ))
    assert resp.decision.value == "kill"


@pytest.mark.asyncio
async def test_ad_guard_ledger_event(tmp_path: Path):
    db = tmp_path / "ad.sqlite"
    ledger = AppendOnlyLedger(db, async_writes=True)
    ledger.start_async_writer()
    gw = AdGuardGateway(ledger=ledger, shadow_mode=True)
    await gw.evaluate(AdSpendRequest(
        client_id="agency",
        method="POST",
        path="/mutate",
        body={"campaign_id": "c9", "bid_amount": 5.0},
        provider="generic",
    ))
    ledger.stop_async_writer(flush=True)
    entries = ledger.list_entries()
    spend_events = [e for e in entries if e.get("event_type") == "ad_spend_request"]
    assert spend_events
    payload = spend_events[0]["payload"]
    assert payload["campaign_id"] == "c9"
    assert ledger.verify()["chain_ok"]


@pytest.mark.asyncio
async def test_ad_guard_reject_logs_to_ledger(tmp_path: Path):
    db = tmp_path / "ad.sqlite"
    ledger = AppendOnlyLedger(db, async_writes=True)
    ledger.start_async_writer()
    from inst_spine.rates import MemoryIdempotencyBackend

    gw = AdGuardGateway(
        ledger=ledger,
        shadow_mode=True,
        idempotency=MemoryIdempotencyBackend(),
    )
    req = AdSpendRequest(
        client_id="agency",
        method="POST",
        path="/mutate",
        body={"campaign_id": "c1", "bid_amount": 1.0},
        idempotency_key="dup-key",
    )
    await gw.evaluate(req)
    resp = await gw.evaluate(req)
    assert resp.decision.value == "reject"
    ledger.stop_async_writer(flush=True)
    events = [e for e in ledger.list_entries() if e.get("event_type") == "ad_spend_request"]
    assert len(events) >= 2
    assert any(e["payload"]["decision"] == "reject" for e in events)


@pytest.mark.asyncio
async def test_ad_guard_creative_gate_required(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AD_GUARD_REQUIRE_CREATIVE_APPROVAL", "1")
    gw = AdGuardGateway(shadow_mode=True)
    resp = await gw.evaluate(AdSpendRequest(
        client_id="agency",
        method="POST",
        path="/mutate",
        body={"campaign_id": "c1", "bid_amount": 1.0},
    ))
    assert resp.decision.value == "reject"
    assert "NeMo" in resp.reason or "creative" in resp.reason

    resp2 = await gw.evaluate(AdSpendRequest(
        client_id="agency",
        method="POST",
        path="/mutate",
        body={"campaign_id": "c1", "bid_amount": 1.0},
        creative_approved=True,
    ))
    assert resp2.decision.value == "approve"


@pytest.mark.asyncio
async def test_ad_guard_serve_approves(tmp_path: Path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    import ad_guard.serve as serve_mod

    serve_mod.state = serve_mod.RuntimeState()
    serve_mod.state.ledger = AppendOnlyLedger(tmp_path / "serve.sqlite", async_writes=True)
    serve_mod.state.ledger.start_async_writer()
    serve_mod.state.gateway = AdGuardGateway(ledger=serve_mod.state.ledger, shadow_mode=True)

    try:
        with TestClient(serve_mod.app) as client:
            resp = client.post(
                "/v1/guard/agency-1",
                json={"campaignId": "99", "bidMicros": 1_000_000},
                headers={"X-Ad-Provider": "google"},
            )
            assert resp.status_code == 200
            assert resp.json()["decision"] == "approve"
    finally:
        serve_mod.state.ledger.close()
