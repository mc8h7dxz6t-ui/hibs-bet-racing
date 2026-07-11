"""Guided ingest for Proof Console — demo payloads + programmatic ledger append per SKU."""

from __future__ import annotations

import json
import os
import random
import uuid
from pathlib import Path
from typing import Any

from inst_workflow.catalog import ProductCatalogEntry

GUIDED_INGEST_IDS = frozenset(
    {
        "altdata",
        "ai-kit",
        "webhook-mesh",
        "ad-guard",
        "health",
        "model-governor",
        "drift-gate",
        "webhook-replay",
        "spend-guard",
        "agent-ledger",
    }
)


def supports_guided_ingest(product_id: str) -> bool:
    return (product_id or "").strip().lower() in GUIDED_INGEST_IDS


def _model_snapshot() -> dict[str, Any]:
    path = Path("docs/demo_model_snapshot.json")
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return {
        "model_id": "credit-risk-v3",
        "version": "3.2.1",
        "artifact_hash": "sha256:a9a66f691284636e374b3b558954f0fead7331aa50a030966c72c77ab70eeffc",
        "risk_tier": "high",
    }


def demo_payload(entry: ProductCatalogEntry, *, demo_dir: Path) -> dict[str, Any]:
    """Return a copy-paste JSON payload for guided ingest in Proof Console."""
    pid = entry.id
    if pid == "altdata":
        return {
            "feed_id": "demo_feed",
            "ctx": {
                "demo_price": 42.5,
                "demo_seats": 180,
                "route_code": "DEMO-01",
                "raw_html": "<td>42.5</td><td>180</td><td>DEMO-01</td>",
            },
        }
    if pid == "ai-kit":
        return {"agent_id": "demo", "steps": 2, "max_tokens": 256}
    if pid == "webhook-mesh":
        return {
            "tenant_id": "tenant-demo",
            "payload_id": f"evt-proof-{uuid.uuid4().hex[:8]}",
            "body": {"id": "evt-demo-1", "type": "checkout.session.completed"},
            "target_url": "https://httpbin.org/post",
            "status": "ACCEPTED",
        }
    if pid == "ad-guard":
        return {
            "provider": "google",
            "body": {
                "campaignId": "12345",
                "bidMicros": 2_500_000,
                "costMicros": 10_000_000,
            },
            "creative_approved": True,
        }
    if pid == "health":
        return {
            "device_id": "ward-7",
            "packets": [
                {"ts": "2026-06-01T12:00:00Z", "seq": 1, "hr": 72, "spo2": 98},
                {"ts": "2026-06-01T12:00:01Z", "seq": 2, "hr": 73, "spo2": 97},
            ],
            "auto_seq": True,
        }
    if pid == "model-governor":
        return {
            "action": "register",
            "model_snapshot": _model_snapshot(),
            "outcome": {"status": "registered", "ref": "proof-console"},
        }
    if pid == "drift-gate":
        return {
            "model_id": "credit-underwrite-v3",
            "version": "v3.2.1",
            "features": {"income": 50_100, "debt_ratio": 0.36},
            "mode": "shadow",
            "request_id": f"proof-{uuid.uuid4().hex[:8]}",
            "ensure_baseline": True,
        }
    if pid == "webhook-replay":
        return {
            "capture_id": f"evt-replay-{uuid.uuid4().hex[:8]}",
            "tenant_id": "tenant-demo",
            "provider": "stripe",
            "body": {"id": "evt-replay-1", "type": "invoice.paid", "amount": 4200},
        }
    if pid == "spend-guard":
        return {
            "action": "reserve_settle",
            "request_id": f"proof-req-{uuid.uuid4().hex[:8]}",
            "estimated_cost": 25.0,
            "actual_cost": 24.0,
            "wallet_balance": 1000.0,
            "reset_wallet": False,
        }
    if pid == "agent-ledger":
        return {
            "action": "authorize",
            "agent_id": "demo-agent",
            "tool": "read_file",
            "args": {"path": "docs/demo_snapshot.json"},
            "idempotency_key": f"proof-{uuid.uuid4().hex[:8]}",
        }
    raise ValueError(f"no guided ingest payload for {entry.id}")


def ingest_schema(entry: ProductCatalogEntry) -> dict[str, Any]:
    """Short UI hint for the ingest textarea."""
    hints = {
        "altdata": "poll_once — feed_id + ctx (demo_feed ladder fields)",
        "ai-kit": "AgentLoop stub steps → trace ledger",
        "webhook-mesh": "Cold-path ingress ledger append (offline demo)",
        "ad-guard": "AdGuardGateway.evaluate — provider + spend body",
        "health": "ingest_batch — device_id + packets (auto_seq bumps seq)",
        "model-governor": "record_governance_event — action + model_snapshot",
        "drift-gate": "evaluate_model_features — ensures synthetic baseline if missing",
        "webhook-replay": "capture → replay_engine (air-gapped bytes)",
        "spend-guard": "reserve → settle on wallet + ledger",
        "agent-ledger": "authorize (optional complete with permit_id)",
    }
    return {
        "product_id": entry.id,
        "sku": entry.sku,
        "hint": hints.get(entry.id, ""),
        "guided": supports_guided_ingest(entry.id),
    }


def _health_packets_with_seq(
    payload: dict[str, Any], *, device_id: str, database: Path
) -> list[dict[str, Any]]:
    packets = list(payload.get("packets") or [])
    if not payload.get("auto_seq"):
        return packets
    from health_telemetry.sequence import DeviceSequenceStore

    store = DeviceSequenceStore.for_ledger(database)
    last = store.last_seq(device_id)
    base = int(last or 0)
    out: list[dict[str, Any]] = []
    for i, pkt in enumerate(packets, start=1):
        row = dict(pkt)
        row["seq"] = base + i
        out.append(row)
    return out


def _ensure_drift_baseline(demo_dir: Path, payload: dict[str, Any]) -> Path:
    baseline = demo_dir / "drift_baseline.json"
    if baseline.is_file() and not payload.get("ensure_baseline"):
        return baseline
    from drift_gate.baseline import FeatureBaseline

    model_id = str(payload.get("model_id") or "credit-underwrite-v3")
    version = str(payload.get("version") or "v3.2.1")
    means = payload.get("baseline_means") or {"income": 50_000, "debt_ratio": 0.35}
    bl = FeatureBaseline(model_id=model_id, version=version)
    random.seed(42)
    for name, mean in means.items():
        m = float(mean)
        bl.features[name] = [m + random.gauss(0, m * 0.05) for _ in range(100)]
    bl.save(baseline)
    return baseline


async def ingest_product_async(
    entry: ProductCatalogEntry,
    payload: dict[str, Any],
    *,
    demo_dir: Path,
) -> dict[str, Any]:
    """Append one guided ingest event to the SKU ledger (offline-safe)."""
    if not supports_guided_ingest(entry.id):
        raise ValueError(f"guided ingest not supported for {entry.id}")

    demo_dir.mkdir(parents=True, exist_ok=True)
    db = entry.db_path(demo_dir)
    pid = entry.id

    if pid == "ad-guard":
        return await _ingest_ad_guard(payload, db=db, product_id=pid)

    return ingest_product(entry, payload, demo_dir=demo_dir)


def ingest_product(
    entry: ProductCatalogEntry,
    payload: dict[str, Any],
    *,
    demo_dir: Path,
) -> dict[str, Any]:
    """Synchronous ingest — ad-guard uses ingest_product_async."""
    if entry.id == "ad-guard":
        raise ValueError("use ingest_product_async for ad-guard")

    demo_dir.mkdir(parents=True, exist_ok=True)
    db = entry.db_path(demo_dir)
    pid = entry.id

    if not supports_guided_ingest(entry.id):
        raise ValueError(f"guided ingest not supported for {entry.id}")

    if pid == "altdata":
        from altdata.poll import poll_once

        result = poll_once(
            feed_id=str(payload.get("feed_id") or "demo_feed"),
            ctx=dict(payload.get("ctx") or {}),
            database=db,
        )
        return {
            "ok": result.ok,
            "product_id": pid,
            "manifest_id": result.manifest_id,
            "coverage_pct": result.coverage_pct,
            "database": str(db),
        }

    if pid == "ai-kit":
        from ai_kit.pipeline import AgentLoop
        from ai_kit.validate import validate_with_retry
        from inst_spine.ledger import AppendOnlyLedger

        agent_id = str(payload.get("agent_id") or "demo")
        steps = int(payload.get("steps") or 2)
        max_tokens = int(payload.get("max_tokens") or 256)
        checkpoint_db = demo_dir / f"ai_kit_{agent_id}_checkpoint.sqlite"
        trace = AppendOnlyLedger(db, writer_id=agent_id)
        loop = AgentLoop(agent_id=agent_id, checkpoint_db=checkpoint_db, trace_ledger=trace)

        def _step(step: int, state: dict[str, Any]) -> dict[str, Any]:
            raw = json.dumps({"ok": True, "step": step, "max_tokens": max_tokens})
            result = validate_with_retry(
                raw,
                lambda d: d if "ok" in d else (_ for _ in ()).throw(ValueError("missing ok")),
                max_attempts=3,
            )
            if not result.ok:
                raise ValueError(result.error or "validation failed")
            state = dict(state)
            state[f"step_{step}"] = result.value
            return state

        final = loop.run_steps(start_step=0, steps=steps, step_fn=_step)
        return {"ok": True, "product_id": pid, "final_state": final, "database": str(db)}

    if pid == "webhook-mesh":
        from webhook_mesh.audit import append_ingress_event

        body_obj = payload.get("body") or {}
        raw = json.dumps(body_obj, sort_keys=True).encode("utf-8")
        payload_id = str(payload.get("payload_id") or uuid.uuid4().hex)
        manifest_id = str(payload.get("manifest_id") or payload_id)
        prev = os.environ.get("WEBHOOK_MESH_LEDGER")
        os.environ["WEBHOOK_MESH_LEDGER"] = str(db)
        try:
            append_ingress_event(
                manifest_id=manifest_id,
                client_id=str(payload.get("tenant_id") or "tenant-demo"),
                payload_id=payload_id,
                target_url=str(payload.get("target_url") or "https://httpbin.org/post"),
                status=str(payload.get("status") or "ACCEPTED"),
                lamport=int(payload.get("lamport") or 1),
                raw_bytes=raw,
                dispatch_mode="background",
            )
            from inst_spine.ledger_registry import get_ledger

            ledger = get_ledger(db, writer_id="webhook-mesh")
            if hasattr(ledger, "flush_async"):
                ledger.flush_async()
        finally:
            if prev is None:
                os.environ.pop("WEBHOOK_MESH_LEDGER", None)
            else:
                os.environ["WEBHOOK_MESH_LEDGER"] = prev
        return {"ok": True, "product_id": pid, "manifest_id": manifest_id, "database": str(db)}

    if pid == "health":
        from health_telemetry.ingest import ingest_batch

        device_id = str(payload.get("device_id") or "ward-7")
        packets = _health_packets_with_seq(payload, device_id=device_id, database=db)
        entry_row = ingest_batch(device_id=device_id, packets=packets, database=db)
        return {"ok": True, "product_id": pid, "entry": entry_row, "database": str(db)}

    if pid == "model-governor":
        from model_governor.record import record_governance_event

        action = str(payload.get("action") or "register")
        model_snapshot = dict(payload.get("model_snapshot") or _model_snapshot())
        outcome = dict(payload.get("outcome") or {"status": action})
        entry_row = record_governance_event(
            action=action,
            model_snapshot=model_snapshot,
            outcome=outcome,
            actor=str(payload.get("actor") or "proof-console"),
            database=db,
        )
        return {"ok": True, "product_id": pid, "entry": entry_row, "database": str(db)}

    if pid == "drift-gate":
        from drift_gate.integrate import evaluate_model_features

        baseline = _ensure_drift_baseline(demo_dir, payload)
        features = {k: float(v) for k, v in dict(payload.get("features") or {}).items()}
        result = evaluate_model_features(
            model_id=str(payload.get("model_id") or "credit-underwrite-v3"),
            version=str(payload.get("version") or "v3.2.1"),
            features=features,
            baseline_path=baseline,
            mode=str(payload.get("mode") or "shadow"),
            database=db,
            request_id=str(payload.get("request_id") or uuid.uuid4().hex),
            state_path=baseline.with_suffix(".rolling.json"),
        )
        decision = (result.get("response") or {}).get("decision")
        return {
            "ok": True,
            "product_id": pid,
            "decision": decision,
            "baseline": str(baseline),
            "result": result,
            "database": str(db),
        }

    if pid == "webhook-replay":
        from inst_spine.ledger import AppendOnlyLedger
        from webhook_replay.capture import CaptureStore
        from webhook_replay.integrate import capture_from_ingress
        from webhook_replay.replay_engine import ReplayEngine

        cap_dir = demo_dir / "captures"
        cap_dir.mkdir(parents=True, exist_ok=True)
        capture_id = str(payload.get("capture_id") or uuid.uuid4().hex)
        body_obj = payload.get("body") or {}
        body_bytes = json.dumps(body_obj, sort_keys=True).encode("utf-8")
        headers = {str(k): str(v) for k, v in dict(payload.get("headers") or {}).items()}
        if not headers:
            headers = {"X-Webhook-Id": capture_id}
        capture_from_ingress(
            capture_id=capture_id,
            tenant_id=str(payload.get("tenant_id") or "tenant-demo"),
            body=body_bytes,
            headers=headers,
            provider=str(payload.get("provider") or "stripe"),
            store_dir=cap_dir,
        )
        store = CaptureStore(cap_dir)
        cap_path = store._path_for(capture_id)
        ledger = AppendOnlyLedger(db, writer_id="webhook-replay")
        engine = ReplayEngine(store=store, ledger=ledger)
        replay = engine.replay_file(cap_path)
        return {
            "ok": replay.ok,
            "product_id": pid,
            "capture_id": capture_id,
            "replay": replay.to_dict() if hasattr(replay, "to_dict") else {
                "ok": replay.ok,
                "message": replay.message,
            },
            "database": str(db),
        }

    if pid == "spend-guard":
        from inst_spine.ledger import AppendOnlyLedger
        from spend_guard.gateway import SpendGuardGateway, SpendRequest
        from spend_guard.wallet_factory import open_wallet

        wallet_db = demo_dir / "spend_wallet.sqlite"
        action = str(payload.get("action") or "reserve_settle")
        if payload.get("reset_wallet") and wallet_db.exists():
            wallet_db.unlink()
        if not wallet_db.exists():
            open_wallet(
                wallet_db,
                initial_balance=float(payload.get("wallet_balance") or 1000.0),
            )
        wallet = open_wallet(wallet_db)
        ledger = AppendOnlyLedger(db, writer_id="spend-guard")
        gw = SpendGuardGateway(wallet=wallet, ledger=ledger)
        request_id = str(payload.get("request_id") or uuid.uuid4().hex)
        if action == "reserve_settle":
            est = float(payload.get("estimated_cost") or 25.0)
            actual = float(payload.get("actual_cost") or est)
            reserve = gw.reserve(SpendRequest(request_id=request_id, estimated_cost=est))
            settle = None
            if reserve.hold_id:
                settle = gw.settle(
                    reserve.hold_id,
                    actual_cost=actual,
                    request_id=request_id,
                )
            return {
                "ok": reserve.decision.value == "approve",
                "product_id": pid,
                "reserve": reserve.to_dict(),
                "settle": settle.to_dict() if settle else None,
                "wallet_db": str(wallet_db),
                "database": str(db),
            }
        raise ValueError(f"unsupported spend-guard action: {action}")

    if pid == "agent-ledger":
        from agent_ledger.integrate import authorize_tool_call, complete_tool_call

        permit_db = demo_dir / "agent_ledger_permits.sqlite"
        action = str(payload.get("action") or "authorize")
        if action == "authorize":
            result = authorize_tool_call(
                agent_id=str(payload.get("agent_id") or "demo-agent"),
                tool_name=str(payload.get("tool") or "read_file"),
                arguments=dict(payload.get("args") or {}),
                ledger_db=db,
                permit_db=permit_db,
                idempotency_key=payload.get("idempotency_key"),
            )
            return {"ok": result.get("decision") == "permit", "product_id": pid, **result}
        if action == "complete":
            result = complete_tool_call(
                permit_id=str(payload.get("permit_id") or ""),
                result=payload.get("result") or {"status": "ok"},
                ledger_db=db,
                permit_db=permit_db,
            )
            return {"ok": True, "product_id": pid, **result}
        raise ValueError(f"unsupported agent-ledger action: {action}")

    raise ValueError(f"unhandled product {entry.id}")


async def _ingest_ad_guard(payload: dict[str, Any], *, db: Path, product_id: str) -> dict[str, Any]:
    from ad_guard.proxy import AdGuardGateway, AdSpendRequest
    from inst_spine.ledger import AppendOnlyLedger

    ledger = AppendOnlyLedger(db, async_writes=True)
    ledger.start_async_writer()
    gw = AdGuardGateway(ledger=ledger, shadow_mode=True)
    body = dict(payload.get("body") or {})
    req = AdSpendRequest(
        client_id=str(payload.get("client_id") or "agency-1"),
        method=str(payload.get("method") or "POST"),
        path=str(payload.get("path") or "/v1/campaigns/mutate"),
        body=body,
        provider=str(payload.get("provider") or "google"),
        campaign_id=payload.get("campaign_id"),
        idempotency_key=payload.get("idempotency_key"),
        creative_approved=True if payload.get("creative_approved") else None,
    )
    resp = await gw.evaluate(req)
    ledger.stop_async_writer(flush=True)
    return {
        "ok": resp.decision.value == "approve",
        "product_id": product_id,
        "decision": resp.decision.value,
        "reason": resp.reason,
        "database": str(db),
    }
