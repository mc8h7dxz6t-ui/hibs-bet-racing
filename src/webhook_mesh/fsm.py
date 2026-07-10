"""Delivery FSM — RECEIVED → FORWARDING → DELIVERED | DEAD_LETTER."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

import httpx

from webhook_mesh.replay import (
    build_dead_letter_meta,
    can_replay_dead_letter,
    dead_letter_meta_path,
    find_dead_letter_record,
    load_dead_letter_meta,
)

logger = logging.getLogger("webhook_mesh.delivery")

MAX_RETRIES = 3
INITIAL_BACKOFF_SECONDS = 2
SUCCESS_STATUS_CODES = frozenset({200, 201, 202, 204})
DELIVERY_LIMITS = httpx.Limits(max_keepalive_connections=50, max_connections=200)
DELIVERY_TIMEOUT = httpx.Timeout(2.0, connect=1.0)


async def dispatch_webhook_delivery(
    manifest_id: str,
    payload: bytes,
    target_url: str,
    lamport: int,
    *,
    dead_letter_dir: str | Path | None = None,
    payload_id: str = "",
    client_id: str = "",
    dispatch_mode: str = "",
) -> bool:
    from webhook_mesh.audit import append_delivery_event

    append_delivery_event(
        manifest_id=manifest_id,
        client_id=client_id,
        payload_id=payload_id,
        target_url=target_url,
        status="FORWARDING",
        lamport=lamport,
        raw_bytes=payload,
        dispatch_mode=dispatch_mode,
    )
    last_status_code: int | None = None
    async with httpx.AsyncClient(limits=DELIVERY_LIMITS, timeout=DELIVERY_TIMEOUT) as client:
        backoff = INITIAL_BACKOFF_SECONDS
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                logger.info(
                    "DELIVERING_PAYLOAD manifest=%s attempt=%s/%s",
                    manifest_id,
                    attempt,
                    MAX_RETRIES,
                )
                response = await client.post(
                    target_url,
                    content=payload,
                    headers={
                        "Content-Type": "application/json",
                        "X-Inst-Manifest-Id": manifest_id,
                        "X-Inst-Sequence": str(lamport),
                    },
                )
                last_status_code = response.status_code
                if response.status_code in SUCCESS_STATUS_CODES:
                    logger.info("DELIVERY_SUCCESS manifest=%s attempt=%s", manifest_id, attempt)
                    append_delivery_event(
                        manifest_id=manifest_id,
                        client_id=client_id,
                        payload_id=payload_id,
                        target_url=target_url,
                        status="DELIVERED",
                        lamport=lamport,
                        raw_bytes=payload,
                        dispatch_mode=dispatch_mode,
                        extra={"upstream_status": response.status_code, "attempt": attempt},
                    )
                    return True
                logger.warning(
                    "DELIVERY_TRANSIENT_FAILURE manifest=%s status=%s",
                    manifest_id,
                    response.status_code,
                )
            except httpx.RequestError as exc:
                logger.warning(
                    "DELIVERY_NETWORK_DISRUPTION manifest=%s attempt=%s err=%s",
                    manifest_id,
                    attempt,
                    exc,
                )
            if attempt < MAX_RETRIES:
                await asyncio.sleep(backoff)
                backoff *= 2

    logger.error(
        "DELIVERY_PERMANENT_FAILURE manifest=%s dead-lettered status=%s",
        manifest_id,
        last_status_code,
    )
    await handle_dead_letter_allocation(
        manifest_id,
        payload,
        target_url,
        dead_letter_dir=dead_letter_dir,
        payload_id=payload_id,
        last_status_code=last_status_code,
        attempts=MAX_RETRIES,
        client_id=client_id,
        lamport=lamport,
        dispatch_mode=dispatch_mode,
    )
    return False


async def handle_dead_letter_allocation(
    manifest_id: str,
    payload: bytes,
    target_url: str,
    *,
    dead_letter_dir: str | Path | None = None,
    payload_id: str = "",
    last_status_code: int | None = None,
    failure_reason: str = "max_retries_exceeded",
    attempts: int = 0,
    client_id: str = "",
    lamport: int = 0,
    dispatch_mode: str = "",
) -> Path | None:
    from webhook_mesh.audit import append_delivery_event

    meta = build_dead_letter_meta(
        manifest_id=manifest_id,
        payload=payload,
        target_url=target_url,
        payload_id=payload_id,
        last_status_code=last_status_code,
        failure_reason=failure_reason,
        attempts=attempts,
    )
    delivery_status = "POISON" if meta.get("replay_blocked") else "DEAD_LETTER"
    append_delivery_event(
        manifest_id=manifest_id,
        client_id=client_id,
        payload_id=payload_id,
        target_url=target_url,
        status=delivery_status,
        lamport=lamport,
        raw_bytes=payload,
        dispatch_mode=dispatch_mode,
        extra={
            "last_status_code": last_status_code,
            "failure_reason": failure_reason,
            "attempts": attempts,
            "block_reason": meta.get("block_reason"),
        },
    )
    base = Path(dead_letter_dir or "./data/dead_letter")
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"{manifest_id}.bin"
    meta_path = dead_letter_meta_path(
        base,
        manifest_id=manifest_id,
        payload_id=payload_id,
        last_status_code=last_status_code,
    )
    path.write_bytes(payload)
    meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True), encoding="utf-8")
    if meta["replay_blocked"]:
        logger.error(
            "DEAD_LETTER_POISON manifest=%s reason=%s",
            manifest_id,
            meta.get("block_reason"),
        )
    return path


async def replay_dead_letter(
    dead_letter_dir: str | Path,
    *,
    manifest_id: str | None = None,
    payload_id: str | None = None,
    schema_version: str | None = None,
) -> tuple[bool, str]:
    record = find_dead_letter_record(
        dead_letter_dir, manifest_id=manifest_id, payload_id=payload_id
    )
    if record is None:
        return False, "dead_letter_not_found"
    bin_path, meta_path, meta = record
    if schema_version:
        meta = dict(meta)
        meta["schema_version_required"] = schema_version
        meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True), encoding="utf-8")
    allowed, reason = can_replay_dead_letter(meta)
    if not allowed:
        return False, f"replay_blocked:{reason}"
    payload = bin_path.read_bytes()
    target_url = str(meta.get("target_url", ""))
    mid = str(meta.get("manifest_id", manifest_id or payload_id or bin_path.stem))
    pid = str(meta.get("payload_id", payload_id or ""))
    if not target_url:
        return False, "missing_target_url"
    ok = await dispatch_webhook_delivery(
        manifest_id=mid,
        payload=payload,
        target_url=target_url,
        lamport=0,
        dead_letter_dir=dead_letter_dir,
        payload_id=pid,
    )
    if ok:
        return True, "replayed"
    refreshed = load_dead_letter_meta(meta_path) if meta_path.exists() else meta
    if refreshed.get("replay_blocked"):
        return False, f"replay_failed_poison:{refreshed.get('block_reason')}"
    return False, "replay_failed"
