"""Webhook mesh cold-path ledger — genesis audit alongside WAL."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

from inst_spine.ledger import AppendOnlyLedger


def ledger_path() -> Path:
    return Path(os.getenv("WEBHOOK_MESH_LEDGER", "data/webhook_mesh_ledger.sqlite"))


def append_ingress_event(
    *,
    manifest_id: str,
    client_id: str,
    payload_id: str,
    target_url: str,
    status: str,
    lamport: int,
    raw_bytes: bytes,
    dispatch_mode: str,
) -> None:
    """Cold-path genesis ledger append (every accepted ingress)."""
    db = ledger_path()
    ledger = AppendOnlyLedger(db, writer_id="webhook-mesh", async_writes=False)
    payload: dict[str, Any] = {
        "manifest_id": manifest_id,
        "client_id": client_id,
        "payload_id": payload_id,
        "target_url": target_url,
        "status": status,
        "lamport": lamport,
        "dispatch_mode": dispatch_mode,
        "payload_sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "payload_bytes": len(raw_bytes),
    }
    ledger.append(
        event_type="webhook_ingress",
        payload=payload,
        manifest_id=manifest_id,
    )
