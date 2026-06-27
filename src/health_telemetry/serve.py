"""HTTP telemetry gateway — WAL fsync before ack, then sequence-gated ingest."""

from __future__ import annotations

import json
import logging
import os
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, Response, status

from health_telemetry.ingest import ingest_batch
from inst_spine.clocks import LamportClock
from inst_spine.errors import IngestValidationError
from inst_spine.middleware import install_api_key_middleware, verify_device_token
from inst_spine.rates import idempotency_backend_from_env
from inst_spine.wal import WALWriter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("health_telemetry.serve")

app = FastAPI(title="Health Telemetry — WAL-before-ack batch ingress")
install_api_key_middleware(app, env_var="HEALTH_TELEMETRY_API_KEY")


class RuntimeState:
    def __init__(self) -> None:
        self.clock = LamportClock("health-telemetry")
        self.wal_writer: WALWriter | None = None
        self.ledger_db = Path(os.getenv("HEALTH_TELEMETRY_DB", "data/health_telemetry.sqlite"))
        self.default_profile = os.getenv("HEALTH_TELEMETRY_PROFILE", "rpm_standard")
        self.idempotency = idempotency_backend_from_env()


state = RuntimeState()


@app.on_event("startup")
async def startup() -> None:
    default_ingress_wal = state.ledger_db.parent / f"{state.ledger_db.stem}_ingress.wal"
    wal_path = os.getenv("HEALTH_TELEMETRY_INGRESS_WAL_PATH", str(default_ingress_wal))
    state.wal_writer = WALWriter(wal_path)
    state.ledger_db.parent.mkdir(parents=True, exist_ok=True)
    logger.info(
        "Health telemetry ingress online ingress_wal=%s ledger=%s",
        wal_path,
        state.ledger_db,
    )


@app.on_event("shutdown")
async def shutdown() -> None:
    if state.wal_writer:
        state.wal_writer.close()


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "ok": True,
        "product": "health-telemetry",
        "profile": state.default_profile,
        "ledger": str(state.ledger_db),
    }


def _json_response(body: dict[str, Any], code: int) -> Response:
    return Response(content=json.dumps(body), status_code=code, media_type="application/json")


@app.post("/v1/telemetry/batch", status_code=status.HTTP_200_OK, response_model=None)
async def post_telemetry_batch(request: Request) -> dict[str, Any] | Response:
    raw = await request.body()
    try:
        body = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return _json_response({"error": "invalid JSON body"}, status.HTTP_400_BAD_REQUEST)

    if not isinstance(body, dict):
        return _json_response({"error": "JSON object required"}, status.HTTP_400_BAD_REQUEST)

    device_id = str(body.get("device_id") or "").strip()
    packets = body.get("packets")
    profile = str(body.get("profile") or state.default_profile)
    batch_id = str(body.get("batch_id") or request.headers.get("X-Batch-Id") or "").strip()
    idem_key = request.headers.get("X-Idempotency-Key") or (
        f"health:{device_id}:{batch_id}" if device_id and batch_id else ""
    )

    if not device_id:
        return _json_response({"error": "device_id required"}, status.HTTP_400_BAD_REQUEST)
    device_token = (request.headers.get("X-Device-Token") or "").strip()
    if not verify_device_token(device_id, device_token):
        return _json_response({"error": "device authentication failed"}, status.HTTP_401_UNAUTHORIZED)
    if not isinstance(packets, list) or not packets:
        return _json_response({"error": "packets must be a non-empty array"}, status.HTTP_400_BAD_REQUEST)

    if idem_key:
        ttl = int(os.getenv("HEALTH_IDEMPOTENCY_TTL_SECONDS", "86400"))
        is_unique = await state.idempotency.consume_idempotency_token(idem_key, ttl_seconds=ttl)
        if not is_unique:
            return {
                "status": "ALREADY_PROCESSED",
                "device_id": device_id,
                "batch_id": batch_id or None,
            }

    assert state.wal_writer is not None
    state.clock.tick()
    receipt_id = batch_id or str(uuid.uuid4())
    state.wal_writer.append(
        payload={
            "receipt_id": receipt_id,
            "device_id": device_id,
            "packet_count": len(packets),
            "profile": profile,
            "status": "RECEIVED",
            "lamport": state.clock.value,
        },
        lamport=state.clock.value,
        raw_bytes=raw,
    )

    try:
        entry = ingest_batch(
            device_id=device_id,
            packets=packets,
            database=state.ledger_db,
            profile=profile,
            actor="health-telemetry-http",
        )
    except IngestValidationError as exc:
        logger.warning("ingest rejected device=%s: %s", device_id, exc)
        return _json_response(
            {"error": str(exc), "device_id": device_id, "wal_acked": True},
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    return {
        "status": "ACCEPTED",
        "receipt_id": receipt_id,
        "device_id": device_id,
        "lamport": state.clock.value,
        "entry_id": entry.get("entry_id"),
        "coverage_pct": entry.get("coverage_pct"),
        "sequence": entry.get("sequence"),
    }


def main() -> None:
    import uvicorn

    host = os.getenv("HEALTH_TELEMETRY_HOST", "127.0.0.1")
    port = int(os.getenv("HEALTH_TELEMETRY_PORT", "8793"))
    uvicorn.run("health_telemetry.serve:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
