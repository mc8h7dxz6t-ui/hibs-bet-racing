"""Delivery FSM — RECEIVED → FORWARDING → DELIVERED | DEAD_LETTER."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import httpx

logger = logging.getLogger("webhook_mesh.delivery")

MAX_RETRIES = 3
INITIAL_BACKOFF_SECONDS = 2
SUCCESS_STATUS_CODES = frozenset({200, 201, 202, 204})


async def dispatch_webhook_delivery(
    manifest_id: str,
    payload: bytes,
    target_url: str,
    lamport: int,
    *,
    dead_letter_dir: str | Path | None = None,
) -> bool:
    """
    Headless delivery with exponential backoff. Returns True if delivered.
    """
    async with httpx.AsyncClient(timeout=5.0) as client:
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
                if response.status_code in SUCCESS_STATUS_CODES:
                    logger.info(
                        "DELIVERY_SUCCESS manifest=%s attempt=%s",
                        manifest_id,
                        attempt,
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
        "DELIVERY_PERMANENT_FAILURE manifest=%s dead-lettered",
        manifest_id,
    )
    await handle_dead_letter_allocation(
        manifest_id,
        payload,
        target_url,
        dead_letter_dir=dead_letter_dir,
    )
    return False


async def handle_dead_letter_allocation(
    manifest_id: str,
    payload: bytes,
    target_url: str,
    *,
    dead_letter_dir: str | Path | None = None,
) -> Path | None:
    """Persist failed delivery for operator replay."""
    base = Path(dead_letter_dir or "./data/dead_letter")
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"{manifest_id}.bin"
    meta_path = base / f"{manifest_id}.meta.txt"
    path.write_bytes(payload)
    meta_path.write_text(f"target_url={target_url}\n", encoding="utf-8")
    return path
