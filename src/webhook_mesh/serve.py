"""FastAPI ingress — signature → idempotency CAS → WAL fsync → async forward."""

from __future__ import annotations

import json
import logging
import os
import sys
import uuid
from typing import Any

from fastapi import BackgroundTasks, FastAPI, Request, Response, status

from inst_spine.clocks import LamportClock
from inst_spine.rates import IdempotencyBackend, idempotency_backend_from_env
from inst_spine.wal import WALWriter
from webhook_mesh.fsm import dispatch_webhook_delivery
from webhook_mesh.hmac_verify import verify_provider_signature

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("webhook_mesh.ingress")

app = FastAPI(title="Inst++ Webhook Idempotency Mesh Engine")


class RuntimeState:
    """Process-wide spine dependencies."""

    def __init__(self) -> None:
        self.clock = LamportClock("webhook-mesh")
        self.wal_writer: WALWriter | None = None
        self.idempotency_db: IdempotencyBackend | None = None
        self.redis_client: Any = None
        self.provider_secret = os.getenv("WEBHOOK_PROVIDER_SECRET", "")
        self.dead_letter_dir = os.getenv("WEBHOOK_DEAD_LETTER_DIR", "./data/dead_letter")


state = RuntimeState()


@app.on_event("startup")
async def initialize_spine_dependencies() -> None:
    from inst_spine.rates import RedisIdempotencyBackend

    if not state.provider_secret:
        logger.critical(
            "CRITICAL_CONFIGURATION_INVALID: WEBHOOK_PROVIDER_SECRET unset."
        )
        sys.exit(1)
    wal_path = os.getenv("INST_WAL_PATH", "./data/webhook_mesh.wal")
    state.wal_writer = WALWriter(wal_path)
    state.idempotency_db = idempotency_backend_from_env()
    if isinstance(state.idempotency_db, RedisIdempotencyBackend):
        state.redis_client = state.idempotency_db.redis
    logger.info("Inst++ webhook ingress online wal=%s", wal_path)


@app.on_event("shutdown")
async def graceful_spine_teardown() -> None:
    if state.wal_writer:
        state.wal_writer.close()
    if state.redis_client:
        await state.redis_client.close()
    logger.info("Inst++ webhook ingress offline.")


def _json_response(body: dict[str, Any], code: int) -> Response:
    return Response(
        content=json.dumps(body),
        status_code=code,
        media_type="application/json",
    )


@app.post("/v1/ingress/{client_id}", status_code=status.HTTP_200_OK, response_model=None)
async def handle_webhook_ingress(
    client_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
) -> dict[str, Any] | Response:
    """
    Sub-millisecond inbound gate: sig → idempotency CAS → WAL fsync → evacuate loop.
    """
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

    idempotency_key = f"idemp:{client_id}:{payload_id}"
    ttl = int(os.getenv("WEBHOOK_IDEMPOTENCY_TTL_SECONDS", "86400"))
    is_unique = await state.idempotency_db.consume_idempotency_token(
        idempotency_key, ttl_seconds=ttl
    )

    if not is_unique:
        # 200 on duplicate — providers (Stripe, etc.) stop retrying on 2xx
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
        },
        lamport=state.clock.value,
        raw_bytes=raw_payload,
    )

    background_tasks.add_task(
        dispatch_webhook_delivery,
        manifest_id=manifest_id,
        payload=raw_payload,
        target_url=target_url,
        lamport=state.clock.value,
        dead_letter_dir=state.dead_letter_dir,
    )

    return {
        "status": "ACCEPTED",
        "manifest_id": manifest_id,
        "lamport": state.clock.value,
    }
