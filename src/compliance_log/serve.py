"""HTTP decision ingest — institutional compliance logger ingress."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request

from compliance_log.export_policy import default_export_policy, write_policy_file
from compliance_log.ingest import log_decision
from inst_spine.errors import IngestValidationError
from inst_spine.health_probes import ledger_chain_ready, postgres_ready_from_env, readiness_payload, sqlite_db_ready
from inst_spine.http_lifecycle import error_envelope, json_response, make_lifespan
from inst_spine.ingress_guard import install_body_size_limit_middleware
from inst_spine.ledger_factory import is_postgres_dsn
from inst_spine.middleware import install_api_key_middleware
from inst_spine.production_profile import postgres_ha_check, production_profile_enabled

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("compliance_log.serve")


class RuntimeState:
    database: str = os.getenv("COMPLIANCE_LOGGER_DATABASE", "data/compliance_ledger.sqlite")
    default_actor: str = os.getenv("COMPLIANCE_LOGGER_DEFAULT_ACTOR", "compliance-http")


state = RuntimeState()


def _flag_mtls() -> bool:
    return os.getenv("INST_MTLS_REQUIRED", "").strip().lower() in ("1", "true", "yes")


def _startup() -> None:
    logger.info("Compliance Logger HTTP ingress online database=%s", state.database)


def _shutdown() -> None:
    return None


app = FastAPI(
    title="Compliance Logger — tamper-evident decision ingest",
    lifespan=make_lifespan(_startup, _shutdown),
)
install_api_key_middleware(
    app,
    env_var="COMPLIANCE_LOGGER_API_KEY",
    require_mtls=_flag_mtls(),
)
install_body_size_limit_middleware(app)


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "ok": True,
        "product": "compliance-logger",
        "database": state.database,
        "auth_required": bool(os.getenv("COMPLIANCE_LOGGER_API_KEY", "").strip()),
        "export_policy": default_export_policy()["protocol"],
    }


@app.get("/ready")
async def ready() -> Any:
    if is_postgres_dsn(state.database):
        db_ok, db_detail = postgres_ready_from_env()
        if not os.getenv("INST_POSTGRES_DSN", "").strip():
            db_ok, db_detail = postgres_ha_check(state.database)
    else:
        db_ok, db_detail = sqlite_db_ready(state.database)
        if production_profile_enabled():
            pg_ok, pg_detail = postgres_ha_check(os.getenv("INST_POSTGRES_DSN", ""))
            if not pg_ok:
                db_ok, db_detail = pg_ok, pg_detail
    chain_ok, chain_detail = ledger_chain_ready(state.database)
    policy_path = Path(state.database).parent / "export_policy.json" if not is_postgres_dsn(state.database) else Path("data/export_policy.json")
    if not policy_path.is_file():
        write_policy_file(policy_path)
    policy_ok = policy_path.is_file() and policy_path.stat().st_size > 0
    body = readiness_payload(
        product="compliance-logger",
        checks={
            "database": (db_ok, db_detail),
            "ledger_chain": (chain_ok, chain_detail),
            "export_policy": (policy_ok, "export_policy.json" if policy_ok else "missing"),
        },
        extra={"production_profile": production_profile_enabled()},
    )
    return json_response(body, status_code=200 if body["ready"] else 503)


@app.post("/v1/decisions")
async def ingest_decision(request: Request) -> Any:
    try:
        body = await request.json()
    except Exception:
        return error_envelope(code="INVALID_JSON", message="request body must be JSON")

    if not isinstance(body, dict):
        return error_envelope(code="INVALID_JSON", message="JSON object required")

    snapshot = body.get("snapshot")
    outcome = body.get("outcome")
    if not isinstance(snapshot, dict):
        return error_envelope(code="SCHEMA_ERROR", message="snapshot must be a JSON object")
    if not isinstance(outcome, dict):
        return error_envelope(code="SCHEMA_ERROR", message="outcome must be a JSON object")

    actor = str(body.get("actor") or state.default_actor)
    db: str | Path = state.database if is_postgres_dsn(state.database) else Path(state.database)
    try:
        entry = log_decision(
            snapshot=snapshot,
            outcome=outcome,
            actor=actor,
            database=db,
        )
    except IngestValidationError as exc:
        return error_envelope(code="INGEST_VALIDATION", message=str(exc), status_code=422)

    return json_response({"ok": True, "entry": entry})


def main() -> None:
    import uvicorn

    host = os.getenv("COMPLIANCE_LOGGER_HOST", "127.0.0.1")
    port = int(os.getenv("COMPLIANCE_LOGGER_PORT", "8794"))
    uvicorn.run("compliance_log.serve:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
