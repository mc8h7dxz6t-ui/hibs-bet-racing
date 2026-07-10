"""HTTP guard proxy — evaluate outbound marketing API calls."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from fastapi import FastAPI, Request, Response, status

from ad_guard.creative import parse_creative_approved
from ad_guard.proxy import AdGuardGateway, AdSpendRequest
from inst_spine.ledger import AppendOnlyLedger
from inst_spine.middleware import install_api_key_middleware, install_proxy_client_auth_middleware

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("ad_guard.serve")

app = FastAPI(title="Ad-Tech Budget Guardrail")
install_api_key_middleware(app, env_var="AD_GUARD_API_KEY")
install_proxy_client_auth_middleware(app)


class RuntimeState:
    def __init__(self) -> None:
        self.gateway: AdGuardGateway | None = None
        self.ledger: AppendOnlyLedger | None = None
        self.shadow_mode = os.getenv("AD_GUARD_SHADOW", "1") != "0"


state = RuntimeState()


@app.on_event("startup")
async def startup() -> None:
    db_path = os.getenv("AD_GUARD_DATABASE", "data/ad_guard_ledger.sqlite")
    state.ledger = AppendOnlyLedger(db_path, async_writes=True)
    state.ledger.start_async_writer()
    state.gateway = AdGuardGateway(ledger=state.ledger, shadow_mode=state.shadow_mode)
    logger.info(
        "Ad Guard online db=%s shadow=%s",
        db_path,
        state.shadow_mode,
    )


@app.on_event("shutdown")
async def shutdown() -> None:
    if state.ledger:
        state.ledger.stop_async_writer(flush=True)


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"ok": True, "product": "ad-guard", "shadow": state.shadow_mode}


@app.post("/v1/guard/{client_id}", response_model=None)
async def guard_spend(client_id: str, request: Request) -> dict[str, Any] | Response:
    assert state.gateway is not None
    try:
        body = await request.json()
    except Exception:
        return Response(
            content='{"error":"invalid JSON body"}',
            status_code=status.HTTP_400_BAD_REQUEST,
            media_type="application/json",
        )
    if not isinstance(body, dict):
        return Response(
            content='{"error":"body must be a JSON object"}',
            status_code=status.HTTP_400_BAD_REQUEST,
            media_type="application/json",
        )

    provider = request.headers.get("X-Ad-Provider", body.get("provider", "generic"))
    campaign_id = request.headers.get("X-Campaign-Id") or body.get("campaign_id")
    creative_approved = parse_creative_approved(dict(request.headers))
    req = AdSpendRequest(
        client_id=client_id,
        method=request.headers.get("X-Http-Method", "POST"),
        path=request.headers.get("X-Api-Path", "/v1/campaigns/mutate"),
        body=body,
        provider=str(provider),
        campaign_id=str(campaign_id) if campaign_id else None,
        idempotency_key=request.headers.get("X-Idempotency-Key"),
        creative_approved=creative_approved,
    )
    resp = await state.gateway.evaluate(req)
    payload = {
        "decision": resp.decision.value,
        "reason": resp.reason,
        "shadow": state.shadow_mode,
    }
    code = status.HTTP_200_OK
    if resp.decision.value == "reject":
        code = status.HTTP_429_TOO_MANY_REQUESTS
    elif resp.decision.value == "kill":
        code = status.HTTP_503_SERVICE_UNAVAILABLE
    return Response(
        content=json.dumps(payload),
        status_code=code,
        media_type="application/json",
    )


async def run_server(*, host: str = "0.0.0.0", port: int = 8788) -> None:
    import uvicorn

    await uvicorn.Server(
        uvicorn.Config(app, host=host, port=port, log_level="info")
    ).serve()


def main() -> None:
    if not os.getenv("AD_GUARD_DATABASE"):
        os.environ.setdefault("AD_GUARD_DATABASE", "data/ad_guard_ledger.sqlite")
    import uvicorn

    host = os.getenv("AD_GUARD_HOST", "0.0.0.0")
    port = int(os.getenv("AD_GUARD_PORT", "8788"))
    uvicorn.run("ad_guard.serve:app", host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
