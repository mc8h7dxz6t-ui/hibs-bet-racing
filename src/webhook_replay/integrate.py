"""Capture hooks for Webhook Mesh WAL integration."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from webhook_replay.capture import CaptureManifest, CaptureStore


def capture_from_ingress(
    *,
    capture_id: str,
    tenant_id: str,
    body: bytes,
    headers: dict[str, str],
    provider: str = "generic",
    lamport_seq: int = 0,
    target_forward_url: str = "",
    store_dir: Path,
) -> Path:
    """Drop-in after Webhook Mesh HMAC verify — before HTTP 200."""
    store = CaptureStore(store_dir)
    manifest = CaptureManifest(
        capture_id=capture_id,
        tenant_id=tenant_id,
        provider=provider,
        headers=headers,
        received_at_utc=datetime.now(timezone.utc).isoformat(),
        lamport_seq=lamport_seq,
        target_forward_url=target_forward_url,
    )
    return store.write(manifest, body)


def import_wal_record(record: dict[str, Any], *, store_dir: Path) -> Path | None:
    """Import a Webhook Mesh WAL JSON line into capture store."""
    capture_id = str(record.get("webhook_id") or record.get("manifest_id") or "")
    if not capture_id:
        return None
    body_hex = record.get("payload_sha256")
    body = record.get("raw_body")
    if isinstance(body, str):
        body_bytes = body.encode("utf-8")
    elif isinstance(body, bytes):
        body_bytes = body
    else:
        body_bytes = b"{}"
    headers = {str(k): str(v) for k, v in (record.get("headers") or {}).items()}
    return capture_from_ingress(
        capture_id=capture_id,
        tenant_id=str(record.get("tenant_id") or record.get("client_id") or ""),
        body=body_bytes,
        headers=headers,
        provider=str(record.get("provider") or "generic"),
        lamport_seq=int(record.get("lamport_seq") or 0),
        target_forward_url=str(record.get("target_forward_url") or ""),
        store_dir=store_dir,
    )
