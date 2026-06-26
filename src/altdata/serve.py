"""Secured read API — last verified snapshot from ledger."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request

from inst_spine.ledger import AppendOnlyLedger
from inst_spine.rates import TokenBucket, token_bucket_backend_from_env

app = FastAPI(title="Alt-Data — secured feed read API")


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
    ledger = AppendOnlyLedger(_ledger_db())
    for row in reversed(ledger.list_entries()):
        if row.get("event_type") != "snapshot":
            continue
        payload = row.get("payload") or {}
        if str(payload.get("feed_id") or payload.get("device_id") or "") not in ("", feed_id):
            meta_feed = (row.get("metadata") or {}).get("feed_id")
            if str(meta_feed or "") != feed_id and feed_id not in str(payload):
                continue
        return {
            "entry_id": row.get("entry_id"),
            "manifest_id": row.get("manifest_id"),
            "payload": payload,
            "metadata": row.get("metadata") or {},
        }
    raise HTTPException(status_code=404, detail=f"no snapshot for feed {feed_id!r}")


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"ok": True, "service": "altdata"}


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
