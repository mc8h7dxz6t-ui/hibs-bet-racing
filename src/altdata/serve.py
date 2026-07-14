"""Alt-Data secured read API — feed snapshots with production profile probes."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request

from inst_spine.health_probes import ledger_chain_ready, readiness_payload, sqlite_db_ready
from inst_spine.http_lifecycle import json_response
from inst_spine.ingress_guard import install_body_size_limit_middleware
from inst_spine.ledger_registry import get_ledger
from inst_spine.middleware import install_api_key_middleware
from inst_spine.production_profile import redis_production_check
from inst_spine.rates import TokenBucket, token_bucket_backend_from_env

app = FastAPI(title="Alt-Data — secured feed read API")
install_api_key_middleware(app, env_var="ALTDATA_API_KEY")
install_body_size_limit_middleware(app)


def _ledger_db() -> Path:
    return Path(os.getenv("ALTDATA_LEDGER_DB", "data/altdata.sqlite"))


def _rate_limit(request: Request) -> None:
    client = request.headers.get("X-Client-Id") or request.client.host if request.client else "anon"
    bucket = TokenBucket(
        capacity=float(os.getenv("ALTDATA_RATE_CAPACITY", "30")),
        refill_rate=float(os.getenv("ALTDATA_RATE_REFILL", "5")),
        key=f"altdata:{client}",
        backend=token_bucket_backend_from_env(),
    )
    if not bucket.consume(1.0):
        raise HTTPException(status_code=429, detail="rate limit exceeded")


def _last_snapshot(feed_id: str) -> dict[str, Any]:
    ledger = get_ledger(_ledger_db())
    for row in reversed(ledger.list_entries()):
        if row.get("event_type") != "snapshot":
            continue
        payload = row.get("payload") or {}
        if str(payload.get("feed_id") or payload.get("device_id") or "") not in ("", feed_id):
            meta_feed = (row.get("metadata") or {}).get("feed_id")
            if str(meta_feed or "") != feed_id and feed_id not in str(payload):
                continue
        meta = dict(row.get("metadata") or {})
        record = payload.get("record") or {}
        rescue = (record.get("_meta") or {}).get("rescue_fields") or []
        if rescue:
            meta.setdefault("rescue_fields", rescue)
            meta["rescue_rate_documented"] = True
        return {
            "entry_id": row.get("entry_id"),
            "manifest_id": row.get("manifest_id"),
            "payload": payload,
            "metadata": meta,
        }
    raise HTTPException(status_code=404, detail=f"no snapshot for feed {feed_id!r}")


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "ok": True,
        "service": "altdata",
        "auth_required": bool(os.getenv("ALTDATA_API_KEY", "").strip()),
    }


@app.get("/ready")
async def ready() -> Any:
    db_ok, db_detail = sqlite_db_ready(_ledger_db())
    chain_ok, chain_detail = ledger_chain_ready(_ledger_db())
    redis_ok, redis_detail = redis_production_check()
    body = readiness_payload(
        product="altdata",
        checks={
            "ledger_db": (db_ok, db_detail),
            "ledger_chain": (chain_ok, chain_detail),
            "redis_rate_limit": (redis_ok, redis_detail),
        },
    )
    return json_response(body, status_code=200 if body["ready"] else 503)


@app.get("/v1/feed/{feed_id}")
async def get_feed(feed_id: str, request: Request) -> dict[str, Any]:
    _rate_limit(request)
    snap = _last_snapshot(feed_id)
    return {"ok": True, "feed_id": feed_id, "snapshot": snap}


def main() -> None:
    import uvicorn

    host = os.getenv("ALTDATA_HOST", "127.0.0.1")
    port = int(os.getenv("ALTDATA_PORT", "8791"))
    uvicorn.run("altdata.serve:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
