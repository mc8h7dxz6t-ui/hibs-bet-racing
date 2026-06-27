"""Agent permit TTL sweep — Wave 1."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from agent_ledger.permits import PermitStore


def test_permit_expires_and_sweep(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AGENT_LEDGER_PERMIT_TTL_SECONDS", "1")
    store = PermitStore(tmp_path / "permits.sqlite")
    rec = store.create_permit(
        agent_id="a1",
        tool_name="read_file",
        decision="permit",
        reason="ok",
    )
    assert store.get(rec.permit_id) is not None

    # Force expiry in DB
    with store._connect() as conn:
        expired = (datetime.now(timezone.utc) - timedelta(seconds=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
        conn.execute(
            "UPDATE agent_permits SET expires_at = ? WHERE permit_id = ?",
            (expired, rec.permit_id),
        )

    swept = store.sweep_expired()
    assert swept >= 1
    ok, reason = store.complete(rec.permit_id)
    assert ok is False
    assert reason == "permit_expired"
