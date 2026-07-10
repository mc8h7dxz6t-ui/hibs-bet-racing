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
from inst_spine.health_probes import readiness_payload, redis_ready_from_env
from inst_spine.http_lifecycle import make_lifespan
from inst_spine.middleware import install_api_key_middleware
from inst_spine.rates import IdempotencyBackend, RedisIdempotencyBackend, idempotency_backend_from_env
from inst_spine.wal import WALWriter
from webhook_mesh.hmac_verify import verify_webhook_signature
from webhook_mesh.audit import append_ingress_event
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


async def _noop_handler(**_kwargs: Any) -> bool:
    return True


async def _startup() -> None:
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


async def _shutdown() -> None:
    if state.delivery_queue:
        await state.delivery_queue.stop_worker()
    if state.wal_writer:
        state.wal_writer.close()
    if state.redis_client:
        await state.redis_client.close()


app = FastAPI(
    title="Webhook Idempotency Mesh Engine",
    lifespan=make_lifespan(_startup, _shutdown),
)
install_api_key_middleware(
    app,
    env_var="WEBHOOK_MESH_API_KEY",
    skip_prefixes=("/static", "/v1/ingress"),
)


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"ok": True, "product": "webhook-mesh", "dispatch_mode": state.dispatch_mode}


@app.get("/ready")
async def ready() -> Response:
    wal_ok = state.wal_writer is not None
    secret_ok = bool(state.provider_secret)
    redis_ok, redis_detail = redis_ready_from_env()
    redis_required = state.dispatch_mode == "redis"
    if redis_required and not os.getenv("INST_REDIS_URL", "").strip():
        redis_ok, redis_detail = False, "INST_REDIS_URL required for redis dispatch"
    queue_ok = state.delivery_queue is not None
    body = readiness_payload(
        product="webhook-mesh",
        checks={
            "provider_secret": (secret_ok, "configured" if secret_ok else "WEBHOOK_PROVIDER_SECRET unset"),
            "ingress_wal": (wal_ok, "wal_online" if wal_ok else "wal_not_initialized"),
            "delivery_queue": (queue_ok, "queue_online" if queue_ok else "queue_not_initialized"),
            "redis_profile": (redis_ok, redis_detail),
        },
        extra={"dispatch_mode": state.dispatch_mode, "redis_required": redis_required},
    )
    code = status.HTTP_200_OK if body["ready"] else status.HTTP_503_SERVICE_UNAVAILABLE
    return Response(content=json.dumps(body), status_code=code, media_type="application/json")


def _json_response(body: dict[str, Any], code: int) -> Response:
    return Response(content=json.dumps(body), status_code=code, media_type="application/json")


@app.post("/v1/ingress/{client_id}", status_code=status.HTTP_200_OK, response_model=None)
async def handle_webhook_ingress(
    client_id: str,
    request: Request,
) -> dict[str, Any] | Response:
    return await _handle_ingress(
        client_id,
        request,
        signature_header="X-Provider-Signature",
        webhook_id_header="X-Webhook-Id",
    )


@app.post("/v1/ingress/stripe/{client_id}", status_code=status.HTTP_200_OK, response_model=None)
async def handle_stripe_ingress(
    client_id: str,
    request: Request,
) -> dict[str, Any] | Response:
    """Stripe-compatible route — ``Stripe-Signature`` + ``Stripe-Event-Id``."""
    return await _handle_ingress(
        client_id,
        request,
        signature_header="Stripe-Signature",
        webhook_id_header="Stripe-Event-Id",
        signature_provider="stripe",
        payload_id_json_key="id",
    )


@app.post("/v1/ingress/shopify/{client_id}", status_code=status.HTTP_200_OK, response_model=None)
async def handle_shopify_ingress(
    client_id: str,
    request: Request,
) -> dict[str, Any] | Response:
    """Shopify-compatible route — ``X-Shopify-Hmac-Sha256`` + webhook id."""
    return await _handle_ingress(
        client_id,
        request,
        signature_header="X-Shopify-Hmac-Sha256",
        webhook_id_header="X-Shopify-Webhook-Id",
        signature_provider="shopify",
        payload_id_json_key="id",
    )


async def _handle_ingress(
    client_id: str,
    request: Request,
    *,
    signature_header: str,
    webhook_id_header: str,
    signature_provider: str = "generic",
    payload_id_json_key: str | None = None,
) -> dict[str, Any] | Response:
    provider_sig = request.headers.get(signature_header, "")
    raw_payload = await request.body()
    payload_id = request.headers.get(webhook_id_header, "") or request.headers.get("X-Webhook-Id", "")
    if not payload_id and payload_id_json_key:
        try:
            body = json.loads(raw_payload.decode("utf-8"))
            if isinstance(body, dict):
                payload_id = str(body.get(payload_id_json_key) or "")
        except (json.JSONDecodeError, UnicodeDecodeError):
            payload_id = ""
    target_url = request.headers.get("X-Target-Forward-Url", "")

    if not payload_id or not target_url:
        return _json_response(
            {"error": "Missing webhook id or X-Target-Forward-Url."},
            status.HTTP_400_BAD_REQUEST,
        )

    if not verify_webhook_signature(
        raw_payload,
        provider_sig,
        state.provider_secret,
        provider=signature_provider,
    ):
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

    capture_dir = os.getenv("WEBHOOK_REPLAY_CAPTURE_DIR", "").strip()
    if capture_dir:
        try:
            from pathlib import Path

            from webhook_replay.integrate import capture_from_ingress

            capture_from_ingress(
                capture_id=payload_id,
                tenant_id=client_id,
                body=raw_payload,
                headers={
                    signature_header: provider_sig,
                    webhook_id_header: payload_id,
                    "X-Target-Forward-Url": target_url,
                },
                provider=signature_provider,
                lamport_seq=state.clock.value,
                target_forward_url=target_url,
                store_dir=Path(capture_dir),
            )
        except Exception:
            logger.exception("webhook-replay capture failed (ingress already WAL-acked)")

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

    try:
        append_ingress_event(
            manifest_id=manifest_id,
            client_id=client_id,
            payload_id=payload_id,
            target_url=target_url,
            status="RECEIVED",
            lamport=state.clock.value,
            raw_bytes=raw_payload,
            dispatch_mode=state.dispatch_mode,
        )
    except Exception:
        logger.exception("ledger append failed (ingress already WAL-acked)")

    return {
        "status": "ACCEPTED",
        "manifest_id": manifest_id,
        "lamport": state.clock.value,
        "dispatch_mode": state.dispatch_mode,
    }
