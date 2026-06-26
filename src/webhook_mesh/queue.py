"""Durable delivery queue — Redis Stream (production) or in-process (development)."""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

logger = logging.getLogger("webhook_mesh.queue")

DeliveryHandler = Callable[..., Awaitable[bool]]
STREAM_KEY = "inst:webhook:delivery"
CONSUMER_GROUP = "webhook-workers"


@dataclass(frozen=True)
class DeliveryManifest:
    manifest_id: str
    payload: bytes
    target_url: str
    lamport: int
    client_id: str = ""
    payload_id: str = ""
    dead_letter_dir: str = "./data/dead_letter"

    def to_stream_fields(self) -> dict[str, str]:
        return {
            "manifest_id": self.manifest_id,
            "payload_b64": base64.b64encode(self.payload).decode("ascii"),
            "target_url": self.target_url,
            "lamport": str(self.lamport),
            "client_id": self.client_id,
            "payload_id": self.payload_id,
            "dead_letter_dir": self.dead_letter_dir,
        }

    @classmethod
    def from_stream_fields(cls, fields: dict[str, str]) -> DeliveryManifest:
        return cls(
            manifest_id=fields["manifest_id"],
            payload=base64.b64decode(fields["payload_b64"]),
            target_url=fields["target_url"],
            lamport=int(fields["lamport"]),
            client_id=fields.get("client_id", ""),
            payload_id=fields.get("payload_id", ""),
            dead_letter_dir=fields.get("dead_letter_dir", "./data/dead_letter"),
        )


class DeliveryQueueBackend(ABC):
    @abstractmethod
    async def enqueue(self, manifest: DeliveryManifest) -> None:
        ...

    async def start_worker(self, handler: DeliveryHandler) -> None:
        return None

    async def stop_worker(self) -> None:
        return None


class BackgroundDeliveryQueue(DeliveryQueueBackend):
    """Dev/low-volume — tasks lost on crash (documented)."""

    def __init__(self) -> None:
        self._tasks: set[asyncio.Task[Any]] = set()

    async def enqueue(self, manifest: DeliveryManifest) -> None:
        from webhook_mesh.fsm import dispatch_webhook_delivery

        task = asyncio.create_task(
            dispatch_webhook_delivery(
                manifest_id=manifest.manifest_id,
                payload=manifest.payload,
                target_url=manifest.target_url,
                lamport=manifest.lamport,
                dead_letter_dir=manifest.dead_letter_dir,
                payload_id=manifest.payload_id,
                client_id=manifest.client_id,
                dispatch_mode="background",
            ),
            name=f"delivery-{manifest.manifest_id}",
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def stop_worker(self) -> None:
        if not self._tasks:
            return
        pending = list(self._tasks)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        self._tasks.clear()


class RedisStreamDeliveryQueue(DeliveryQueueBackend):
    """Production — XADD enqueue, XREADGROUP worker, XAUTOCLAIM recovery."""

    def __init__(
        self,
        redis_client: Any,
        *,
        stream_key: str = STREAM_KEY,
        claim_idle_ms: int | None = None,
    ) -> None:
        self.redis = redis_client
        self.stream_key = stream_key
        self.claim_idle_ms = claim_idle_ms or int(
            os.getenv("WEBHOOK_STREAM_CLAIM_IDLE_MS", "30000")
        )
        self._consumer_name = f"worker-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        self._worker_task: asyncio.Task[Any] | None = None
        self._running = False

    async def _ensure_group(self) -> None:
        try:
            await self.redis.xgroup_create(
                self.stream_key, CONSUMER_GROUP, id="0", mkstream=True
            )
        except Exception as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    async def enqueue(self, manifest: DeliveryManifest) -> None:
        await self._ensure_group()
        await self.redis.xadd(self.stream_key, manifest.to_stream_fields())

    async def start_worker(self, handler: DeliveryHandler) -> None:
        if self._worker_task is not None:
            return
        await self._ensure_group()
        self._running = True
        self._worker_task = asyncio.create_task(self._consume_loop(), name="webhook-worker")

    async def stop_worker(self) -> None:
        self._running = False
        if self._worker_task is None:
            return
        self._worker_task.cancel()
        try:
            await self._worker_task
        except asyncio.CancelledError:
            pass
        self._worker_task = None

    async def _reclaim_stale(self) -> list[tuple[str, dict[str, str]]]:
        """Reclaim pending messages from crashed workers (XAUTOCLAIM when available)."""
        reclaimed: list[tuple[str, dict[str, str]]] = []
        try:
            result = await self.redis.xautoclaim(
                self.stream_key,
                CONSUMER_GROUP,
                self._consumer_name,
                min_idle_time=self.claim_idle_ms,
                start_id="0-0",
                count=10,
            )
            # redis-py: (next_start_id, messages, deleted_ids)
            if isinstance(result, (list, tuple)) and len(result) >= 2:
                messages = result[1]
                for message_id, fields in messages or []:
                    reclaimed.append((message_id, fields))
        except AttributeError:
            return reclaimed
        except Exception as exc:
            logger.warning("DELIVERY_RECLAIM_FAILED: %s", exc)
        return reclaimed

    async def _deliver_manifest(self, manifest: DeliveryManifest) -> bool:
        from webhook_mesh.fsm import dispatch_webhook_delivery

        return await dispatch_webhook_delivery(
            manifest_id=manifest.manifest_id,
            payload=manifest.payload,
            target_url=manifest.target_url,
            lamport=manifest.lamport,
            dead_letter_dir=manifest.dead_letter_dir,
            payload_id=manifest.payload_id,
            client_id=manifest.client_id,
            dispatch_mode="redis",
        )

    async def _handle_message(self, message_id: str, fields: dict[str, str]) -> None:
        manifest = DeliveryManifest.from_stream_fields(fields)
        try:
            delivered = await self._deliver_manifest(manifest)
        except Exception as exc:
            logger.error(
                "DELIVERY_WORKER_FAILED manifest=%s err=%s (message left pending)",
                manifest.manifest_id,
                exc,
            )
            return
        # ACK after terminal outcome: success or filesystem DLQ (at-most-once stream).
        await self.redis.xack(self.stream_key, CONSUMER_GROUP, message_id)
        if not delivered:
            logger.warning(
                "DELIVERY_DEAD_LETTERED manifest=%s stream_ack=true",
                manifest.manifest_id,
            )

    async def _consume_loop(self) -> None:
        while self._running:
            try:
                for message_id, fields in await self._reclaim_stale():
                    await self._handle_message(message_id, fields)

                rows = await self.redis.xreadgroup(
                    CONSUMER_GROUP,
                    self._consumer_name,
                    {self.stream_key: ">"},
                    count=10,
                    block=1000,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("DELIVERY_QUEUE_READ_FAILED: %s", exc)
                await asyncio.sleep(1.0)
                continue
            if not rows:
                continue
            for _stream, messages in rows:
                for message_id, fields in messages:
                    await self._handle_message(message_id, fields)


def dispatch_mode_from_env() -> str:
    mode = os.getenv("WEBHOOK_DISPATCH_MODE", "").strip().lower()
    if mode in {"redis", "background"}:
        return mode
    if os.getenv("INST_REDIS_URL", "").strip():
        return "redis"
    return "background"


def delivery_queue_from_env(*, redis_client: Any | None = None) -> DeliveryQueueBackend:
    mode = dispatch_mode_from_env()
    if mode == "redis":
        if redis_client is None:
            url = os.getenv("INST_REDIS_URL", "").strip()
            if not url:
                logger.warning("INST_REDIS_URL unset; using background queue")
                return BackgroundDeliveryQueue()
            try:
                import redis.asyncio as aioredis
            except ImportError as exc:
                raise RuntimeError("Redis queue requires: pip install redis") from exc
            redis_client = aioredis.from_url(url, encoding="utf-8", decode_responses=True)
        return RedisStreamDeliveryQueue(redis_client)
    logger.warning("WEBHOOK_DISPATCH_MODE=background — not durable across restarts")
    return BackgroundDeliveryQueue()
