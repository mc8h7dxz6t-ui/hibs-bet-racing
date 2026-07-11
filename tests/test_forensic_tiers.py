"""Forensic tier implementations — A/B/C/D institutional++ proofs."""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

# Local dev target 10ms; GitHub Actions shared runners are noisy (override via INST_P99_THRESHOLD_MS).
P99_THRESHOLD_MS = float(
    os.environ.get(
        "INST_P99_THRESHOLD_MS",
        "75" if os.environ.get("GITHUB_ACTIONS") else "10",
    )
)

from agent_ledger.gate import gate_from_paths
from agent_ledger.policy import ToolPolicy
from ai_kit.pipeline import AgentLoop, ToolAuthorizationError
from altdata.poll import poll_once
from drift_gate.baseline import FeatureBaseline
from drift_gate.integrate import clear_integrate_cache, evaluate_model_features
from inst_spine.coverage import aggregate_source_coverage
from inst_spine.errors import IngestValidationError
from inst_spine.export import build_audit_bundle
from inst_spine.ledger import AppendOnlyLedger
from inst_spine.retention import build_epoch_compaction_payload, evaluate_retention_policy, merkle_root
from model_governor.record import record_governance_event
from proxy_risk.router import GateDecision, ProxyRequest, ProxyRiskGateway
from spend_guard.wallet import SpendWallet
from spend_guard.gateway import SpendGuardGateway, SpendRequest
from inst_spine.rates import MemoryIdempotencyBackend
from webhook_mesh.audit import append_delivery_event
from webhook_replay.capture import CaptureManifest, CaptureStore
from webhook_replay.replay_engine import ReplayEngine


def test_a1_aggregate_snapshot_coverage():
    entries = [
        {
            "event_type": "snapshot",
            "metadata": {"coverage_pct": 92.0},
        },
        {
            "event_type": "decision",
            "metadata": {"source_coverage_pct": 88.0},
        },
    ]
    assert aggregate_source_coverage(entries) == pytest.approx(88.0)


def test_a2_integrate_rolling_state_persists(tmp_path: Path):
    clear_integrate_cache()
    baseline = tmp_path / "bl.json"
    FeatureBaseline(model_id="m1", version="v1", features={"x": [1.0] * 40}).save(baseline)
    state_path = tmp_path / "rolling.json"
    for i in range(3):
        evaluate_model_features(
            model_id="m1",
            version="v1",
            features={"x": float(i + 1)},
            baseline_path=baseline,
            state_path=state_path,
        )
    clear_integrate_cache()
    evaluate_model_features(
        model_id="m1",
        version="v1",
        features={"x": 99.0},
        baseline_path=baseline,
        state_path=state_path,
    )
    import json

    rolling = json.loads(state_path.read_text(encoding="utf-8"))
    assert len((rolling.get("features") or {}).get("x") or []) >= 3


def test_a3_webhook_delivery_lifecycle_on_ledger(tmp_path: Path, monkeypatch):
    db = tmp_path / "mesh.sqlite"
    monkeypatch.setenv("WEBHOOK_MESH_LEDGER", str(db))
    append_delivery_event(
        manifest_id="m1",
        status="FORWARDING",
        lamport=1,
        raw_bytes=b"{}",
    )
    append_delivery_event(
        manifest_id="m1",
        status="DELIVERED",
        lamport=1,
        raw_bytes=b"{}",
    )
    entries = AppendOnlyLedger(db).list_entries()
    statuses = [
        (e.get("payload") or {}).get("status")
        for e in entries
        if e.get("event_type") == "webhook_delivery"
    ]
    assert statuses == ["FORWARDING", "DELIVERED"]


@pytest.mark.asyncio
async def test_b1_proxy_spend_reserve_gate(tmp_path: Path):
    wallet_db = tmp_path / "wallet.sqlite"
    ledger_db = tmp_path / "spend.sqlite"
    proxy_db = tmp_path / "proxy.sqlite"
    gw = ProxyRiskGateway(
        ledger=AppendOnlyLedger(proxy_db, async_writes=True),
        shadow_mode=False,
        idempotency=MemoryIdempotencyBackend(),
        upstream_base="https://httpbin.org",
        spend_wallet_db=str(wallet_db),
        spend_ledger_db=str(ledger_db),
    )
    gw.ledger.start_async_writer()
    try:
        with patch.object(gw, "_forward_upstream", new=AsyncMock(return_value=(200, {"cost": 0.5}, "ok"))):
            resp = await gw.evaluate(
                ProxyRequest(
                    client_id="c1",
                    method="POST",
                    path="/post",
                    body={"estimated_cost": 1.0},
                    idempotency_key="spend-1",
                )
            )
        assert resp.decision == GateDecision.APPROVE
        wallet = SpendWallet(wallet_db, ledger_db=ledger_db)
        assert wallet.get_state().balance < 1000.0
    finally:
        gw.ledger.stop_async_writer(flush=True)


def test_b2_ai_kit_agent_ledger_authorize(tmp_path: Path):
    trace_db = tmp_path / "trace.sqlite"
    ledger_db = tmp_path / "agent.sqlite"
    permit_db = tmp_path / "permits.sqlite"
    loop = AgentLoop(
        agent_id="demo",
        checkpoint_db=tmp_path / "cp.sqlite",
        trace_ledger=AppendOnlyLedger(trace_db),
        agent_ledger_db=ledger_db,
        agent_permit_db=permit_db,
    )
    policy = ToolPolicy()
    policy.allow_tools = {"read_file"}
    gw = gate_from_paths(ledger_db=ledger_db, permit_db=permit_db, policy=policy)

    def step_fn(step: int, state: dict) -> dict:
        return {**state, "step": step}

    out = loop.run_steps(
        start_step=1,
        steps=1,
        step_fn=step_fn,
        tool_name="read_file",
        tool_arguments={"path": "/tmp/x"},
    )
    assert out["step"] == 1
    entries = AppendOnlyLedger(ledger_db).list_entries()
    assert any(e.get("event_type") == "agent_action" for e in entries)

    with pytest.raises(ToolAuthorizationError):
        loop.run_steps(
            start_step=2,
            steps=1,
            step_fn=step_fn,
            tool_name="transfer_funds",
            tool_arguments={"amount": 100},
        )


def test_b3_model_governor_lifecycle_fsm(tmp_path: Path):
    db = tmp_path / "mg.sqlite"
    from model_governor.integrity import compute_artifact_digest

    base = {
        "model_id": "m",
        "version": "1",
        "risk_tier": "low",
    }
    digest = compute_artifact_digest({**base, "artifact_hash": "pending"})
    snap = {**base, "artifact_hash": f"sha256:{digest}"}
    record_governance_event(action="register", model_snapshot=snap, database=db)
    with pytest.raises(IngestValidationError, match="lifecycle FSM"):
        record_governance_event(action="deploy", model_snapshot=snap, database=db)


def test_a4_spend_drift_survives_rebuild(tmp_path: Path):
    wallet_db = tmp_path / "w.sqlite"
    ledger_db = tmp_path / "l.sqlite"
    wallet = SpendWallet(wallet_db, initial_balance=100.0, drift_threshold_pct=0.3, rolling_window=5)
    gw = SpendGuardGateway(wallet=wallet, ledger=AppendOnlyLedger(ledger_db))
    for i in range(5):
        r = gw.reserve(SpendRequest(request_id=f"r{i}", estimated_cost=1.0))
        assert r.decision.value == "approve"
        gw.settle(r.hold_id or "", actual_cost=1.0, request_id=f"r{i}")
    wallet2 = SpendWallet(wallet_db, ledger_db=ledger_db, drift_threshold_pct=0.3, rolling_window=5)
    assert len(wallet2._spend_history) == 5


@pytest.mark.asyncio
async def test_b4_ad_guard_spend_wallet(tmp_path: Path):
    from ad_guard.proxy import AdGuardGateway, AdSpendRequest

    wallet_db = tmp_path / "wallet.sqlite"
    ledger_db = tmp_path / "spend.sqlite"
    ad_db = tmp_path / "ad.sqlite"
    gw = AdGuardGateway(
        ledger=AppendOnlyLedger(ad_db, async_writes=True),
        shadow_mode=False,
        spend_wallet_db=str(wallet_db),
        spend_ledger_db=str(ledger_db),
    )
    gw.ledger.start_async_writer()
    try:
        with patch.object(gw, "_forward_upstream", new=AsyncMock(return_value=(200, {}, "ok"))):
            resp = await gw.evaluate(
                AdSpendRequest(
                    client_id="c1",
                    method="POST",
                    path="/v1/spend",
                    body={"spend": 5000000},
                    provider="google",
                    campaign_id="camp-1",
                    idempotency_key="ad-1",
                )
            )
        from proxy_risk.router import GateDecision

        assert resp.decision == GateDecision.APPROVE
    finally:
        gw.ledger.stop_async_writer(flush=True)


def test_b5_wrcap_in_bundle_export(tmp_path: Path):
    db = tmp_path / "replay.sqlite"
    cap_dir = tmp_path / "caps"
    store = CaptureStore(cap_dir)
    body = b'{"event":"invoice.paid"}'
    path = store.write(
        CaptureManifest(
            capture_id="cap-1",
            tenant_id="t1",
            provider="stripe",
            headers={},
            received_at_utc="2026-01-01T00:00:00Z",
            lamport_seq=1,
        ),
        body,
    )
    ledger = AppendOnlyLedger(db)
    ledger.append(event_type="webhook_replay", payload={"capture_id": "cap-1"}, manifest_id="cap-1")
    tar = tmp_path / "bundle.tar"
    result = build_audit_bundle(
        db,
        tarball_path=tar,
        product="webhook-replay",
        extra_files={f"wrcap/{path.name}": path},
    )
    assert result.ok
    import tarfile

    with tarfile.open(tar, "r") as tf:
        names = tf.getnames()
    assert any(n.startswith("extras/wrcap/") for n in names)


def test_b5_lamport_replay_attestation(tmp_path: Path):
    mesh_db = tmp_path / "mesh.sqlite"
    replay_db = tmp_path / "replay.sqlite"
    cap_dir = tmp_path / "caps"
    mesh = AppendOnlyLedger(mesh_db)
    mesh.append(
        event_type="webhook_ingress",
        payload={"manifest_id": "cap-1", "lamport": 5},
        manifest_id="cap-1",
    )
    store = CaptureStore(cap_dir)
    manifest = CaptureManifest(
        capture_id="cap-1",
        tenant_id="t1",
        provider="generic",
        headers={},
        received_at_utc="2026-01-01T00:00:00Z",
        lamport_seq=5,
    )
    body = b"{}"
    store.write(manifest, body)
    engine = ReplayEngine(
        store,
        ledger=AppendOnlyLedger(replay_db),
        mesh_ledger_db=mesh_db,
    )
    result = engine.replay_capture(manifest, body)
    assert result.ok


def test_c1_f8_retention_requires_epoch_when_oversize():
    entries = [{"event_type": "decision", "entry_id": str(i), "chain_hash": f"h{i}"} for i in range(60_001)]
    ok, msg = evaluate_retention_policy(entries, max_entries_before_compaction=50_000)
    assert not ok
    root = merkle_root([f"h{i}" for i in range(100)])
    entries.append(
        {
            "event_type": "epoch_compaction",
            "payload": build_epoch_compaction_payload(entries, epoch_id="e1", through_entry_id="99"),
        }
    )
    ok2, _ = evaluate_retention_policy(entries, max_entries_before_compaction=50_000)
    assert ok2


def test_d_spend_reserve_p99_under_10ms(tmp_path: Path):
    wallet_db = tmp_path / "w.sqlite"
    wallet = SpendWallet(wallet_db, initial_balance=100_000.0)
    latencies: list[float] = []
    for i in range(1000):
        t0 = time.perf_counter()
        wallet.reserve(0.01, request_id=f"bench-{i}")
        latencies.append((time.perf_counter() - t0) * 1000)
    latencies.sort()
    p99 = latencies[int(len(latencies) * 0.99) - 1]
    assert p99 < P99_THRESHOLD_MS, f"p99 {p99:.3f}ms exceeds {P99_THRESHOLD_MS}ms"


def test_d_agent_authorize_p99_under_10ms(tmp_path: Path):
    ledger_db = tmp_path / "l.sqlite"
    permit_db = tmp_path / "p.sqlite"
    gw = gate_from_paths(ledger_db=ledger_db, permit_db=permit_db)
    from agent_ledger.gate import AgentActionRequest

    latencies: list[float] = []
    for i in range(500):
        t0 = time.perf_counter()
        gw.authorize(
            AgentActionRequest(
                agent_id="bench",
                tool_name="read_file",
                arguments={"path": f"/tmp/{i}"},
                idempotency_key=f"k-{i}",
            )
        )
        latencies.append((time.perf_counter() - t0) * 1000)
    latencies.sort()
    p99 = latencies[int(len(latencies) * 0.99) - 1]
    assert p99 < P99_THRESHOLD_MS, f"p99 {p99:.3f}ms exceeds {P99_THRESHOLD_MS}ms"


def test_d_altdata_feed_api(tmp_path: Path):
    from fastapi.testclient import TestClient

    from altdata.serve import app

    db = tmp_path / "alt.sqlite"
    poll_once(feed_id="fx_gbp", ctx={"stub": True}, database=db)
    import os

    os.environ["ALTDATA_LEDGER_DB"] = str(db)
    client = TestClient(app)
    r = client.get("/v1/feed/fx_gbp", headers={"X-Client-Id": "test"})
    assert r.status_code == 200
    assert r.json()["feed_id"] == "fx_gbp"
