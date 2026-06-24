"""Tests for Agent Ledger — authorize, complete, policy, permits."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_ledger.gate import AgentActionGate, AgentActionRequest, gate_from_paths
from agent_ledger.permits import PermitStore
from agent_ledger.policy import ToolPolicy
from inst_spine.ledger import AppendOnlyLedger


def test_policy_denies_forbidden_sql():
    policy = ToolPolicy()
    decision, reason = policy.evaluate_tool("sql_select", {"query": "DROP TABLE users"})
    assert decision == "deny"
    assert "forbidden" in reason


def test_policy_escalates_critical_without_human():
    policy = ToolPolicy(agent_tier="break_glass")
    decision, reason = policy.evaluate_tool("transfer_funds", {"amount": 100})
    assert decision == "escalate"
    assert "human" in reason


def test_policy_permits_critical_with_human():
    policy = ToolPolicy(agent_tier="break_glass")
    decision, _ = policy.evaluate_tool(
        "deploy_service",
        {"service": "api", "human_approved": True},
    )
    assert decision == "permit"


def test_authorize_and_complete_chain(tmp_path: Path):
    ledger_db = tmp_path / "ledger.sqlite"
    permit_db = tmp_path / "permits.sqlite"
    gw = gate_from_paths(ledger_db=ledger_db, permit_db=permit_db)

    auth = gw.authorize(
        AgentActionRequest(
            agent_id="test-agent",
            tool_name="read_file",
            arguments={"path": "README.md"},
            idempotency_key="idem-1",
        )
    )
    assert auth.decision.value == "permit"
    assert auth.permit_id == "idem-1"

    done = gw.complete(auth.permit_id or "", result={"ok": True})
    assert done.decision.value == "permit"

    ledger = AppendOnlyLedger(ledger_db)
    phases = [
        e["payload"]["phase"]
        for e in ledger.list_entries()
        if e.get("event_type") == "agent_action"
    ]
    assert phases.count("authorize") >= 1
    assert "complete" in phases


def test_complete_without_permit_denied(tmp_path: Path):
    gw = gate_from_paths(
        ledger_db=tmp_path / "l.sqlite",
        permit_db=tmp_path / "p.sqlite",
    )
    resp = gw.complete("missing-permit", result={"x": 1})
    assert resp.decision.value == "deny"


def test_duplicate_complete_rejected(tmp_path: Path):
    permit_db = tmp_path / "p.sqlite"
    store = PermitStore(permit_db)
    store.create_permit(
        agent_id="a",
        tool_name="read_file",
        decision="permit",
        reason="ok",
        permit_id="p1",
    )
    ok1, _ = store.complete("p1")
    ok2, reason2 = store.complete("p1")
    assert ok1 and not ok2
    assert "status" in reason2


def test_idempotent_authorize(tmp_path: Path):
    gw = gate_from_paths(
        ledger_db=tmp_path / "l.sqlite",
        permit_db=tmp_path / "p.sqlite",
    )
    req = AgentActionRequest(
        agent_id="a",
        tool_name="search_docs",
        arguments={"q": "policy"},
        idempotency_key="same-key",
    )
    r1 = gw.authorize(req)
    r2 = gw.authorize(req)
    assert r1.permit_id == r2.permit_id
    assert "idempotent" in r2.reason


def test_cli_authorize_export_verify(tmp_path: Path):
    from agent_ledger.cli import main

    db = tmp_path / "agent.sqlite"
    permit_db = tmp_path / "permits.sqlite"
    tar = tmp_path / "bundle.tar"

    assert main(
        [
            "authorize",
            "--agent-id",
            "cli-agent",
            "--tool",
            "list_records",
            "--args",
            "{}",
            "--database",
            str(db),
            "--permit-db",
            str(permit_db),
            "--idempotency-key",
            "cli-permit-1",
        ]
    ) == 0

    assert main(
        [
            "complete",
            "--permit-id",
            "cli-permit-1",
            "--result",
            '{"count":3}',
            "--database",
            str(db),
            "--permit-db",
            str(permit_db),
        ]
    ) == 0

    assert main(["check", "--database", str(db)]) == 0
    assert main(["export", "--database", str(db), "--tarball", str(tar)]) == 0
    assert main(["verify-bundle", "--tarball", str(tar)]) == 0
