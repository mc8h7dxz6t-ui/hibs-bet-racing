"""FastAPI ingress — signature → idempotency CAS → WAL fsync → durable queue."""

from __future__ import annotations

import json
import logging
import os
import sys
import uuid
from typing import Any

from fastapi import FastAPI, Request, Response, status

from inst_spine.clocks import LamportClock
from inst_spine.rates import IdempotencyBackend, RedisIdempotencyBackend, idempotency_backend_from_env
from inst_spine.wal import WALWriter
from webhook_mesh.hmac_verify import verify_provider_signature
from webhook_mesh.queue import (
    BackgroundDeliveryQueue,
    DeliveryManifest,
    DeliveryQueueBackend,
    RedisStreamDeliveryQueue,
    delivery_queue_from_env,
    dispatch_mode_from_env,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("webhook_mesh.ingress")

app = FastAPI(title="Inst++ Webhook Idempotency Mesh Engine")


class RuntimeState:
    def __init__(self) -> None:
        self.clock = LamportClock("webhook-mesh")
        self.wal_writer: WALWriter | None = None
        self.idempotency_db: IdempotencyBackend | None = None
        self.delivery_queue: DeliveryQueueBackend | None = None
        self.redis_client: Any = None
        self.provider_secret = os.getenv("WEBHOOK_PROVIDER_SECRET", "")
        self.dead_letter_dir = os.getenv("WEBHOOK_DEAD_LETTER_DIR", "./data/dead_letter")
        self.dispatch_mode = dispatch_mode_from_env()


state = RuntimeState()


@app.on_event("startup")
async def initialize_spine_dependencies() -> None:
    if not state.provider_secret:
        logger.critical("WEBHOOK_PROVIDER_SECRET unset.")
        sys.exit(1)
    wal_path = os.getenv("INST_WAL_PATH", "./data/webhook_mesh.wal")
    state.wal_writer = WALWriter(wal_path)
    state.idempotency_db = idempotency_backend_from_env()
    if isinstance(state.idempotency_db, RedisIdempotencyBackend):
        state.redis_client = state.idempotency_db.redis
    state.delivery_queue = delivery_queue_from_env(redis_client=state.redis_client)
    if isinstance(state.delivery_queue, RedisStreamDeliveryQueue):
        await state.delivery_queue.start_worker(handler=_noop_handler)
        logger.info("Webhook ingress online wal=%s dispatch=redis_stream", wal_path)
    else:
        logger.warning("Webhook ingress online wal=%s dispatch=background", wal_path)


async def _noop_handler(**_kwargs: Any) -> bool:
    return True


@app.on_event("shutdown")
async def graceful_spine_teardown() -> None:
    if state.delivery_queue:
        await state.delivery_queue.stop_worker()
    if state.wal_writer:
        state.wal_writer.close()
    if state.redis_client:
        await state.redis_client.close()


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"ok": True, "product": "webhook-mesh", "dispatch_mode": state.dispatch_mode}


def _json_response(body: dict[str, Any], code: int) -> Response:
    return Response(content=json.dumps(body), status_code=code, media_type="application/json")


@app.post("/v1/ingress/{client_id}", status_code=status.HTTP_200_OK, response_model=None)
async def handle_webhook_ingress(
    client_id: str,
    request: Request,
) -> dict[str, Any] | Response:
    provider_sig = request.headers.get("X-Provider-Signature", "")
    payload_id = request.headers.get("X-Webhook-Id", "")
    target_url = request.headers.get("X-Target-Forward-Url", "")

    if not payload_id or not target_url:
        return _json_response(
            {"error": "Missing X-Webhook-Id or X-Target-Forward-Url."},
            status.HTTP_400_BAD_REQUEST,
        )

    raw_payload = await request.body()
    if not verify_provider_signature(raw_payload, provider_sig, state.provider_secret):
        return _json_response(
            {"error": "Unauthorized: signature verification failed."},
            status.HTTP_401_UNAUTHORIZED,
        )

    assert state.idempotency_db is not None
    assert state.wal_writer is not None
    assert state.delivery_queue is not None

    idempotency_key = f"idemp:{client_id}:{payload_id}"
    ttl = int(os.getenv("WEBHOOK_IDEMPOTENCY_TTL_SECONDS", "86400"))
    is_unique = await state.idempotency_db.consume_idempotency_token(
        idempotency_key, ttl_seconds=ttl
    )
    if not is_unique:
        return {
            "status": "ALREADY_PROCESSED",
            "payload_id": payload_id,
            "client_id": client_id,
        }

    state.clock.tick()
    manifest_id = str(uuid.uuid4())
    state.wal_writer.append(
        payload={
            "manifest_id": manifest_id,
            "client_id": client_id,
            "payload_id": payload_id,
            "target_url": target_url,
            "status": "RECEIVED",
            "lamport": state.clock.value,
            "dispatch_mode": state.dispatch_mode,
        },
        lamport=state.clock.value,
        raw_bytes=raw_payload,
    )

    await state.delivery_queue.enqueue(
        DeliveryManifest(
            manifest_id=manifest_id,
            payload=raw_payload,
            target_url=target_url,
            lamport=state.clock.value,
            client_id=client_id,
            payload_id=payload_id,
            dead_letter_dir=state.dead_letter_dir,
        )
    )

    return {
        "status": "ACCEPTED",
        "manifest_id": manifest_id,
        "lamport": state.clock.value,
        "dispatch_mode": state.dispatch_mode,
    }
