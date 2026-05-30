from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hibs_racing.config import db_path, load_config
from hibs_racing.features.store import connect, init_db
from hibs_racing.live.execution_router import ExecutionIntent, ExecutionResult

EXECUTION_LOG_MIGRATIONS: tuple[tuple[str, str], ...] = ()


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def idempotency_key(runner_id: str, bet_leg: str, venue: str) -> str:
    """Stable key for live dedup — one routed offer per runner leg on a venue."""
    return f"{runner_id}:{bet_leg.lower()}:{venue.lower()}"


def bet_leg_for_intent(intent: ExecutionIntent, *, payload: dict[str, Any] | None = None) -> str:
    if payload and payload.get("bet_leg"):
        return str(payload["bet_leg"])
    bet_type = (intent.bet_type or "each_way").lower()
    if bet_type == "place":
        return "place"
    if bet_type == "win":
        return "win"
    return "win"


def ensure_execution_log_schema(db: Path | None = None) -> Path:
    """Apply feature-store schema including execution_log (safe to re-run)."""
    db = db or db_path(load_config())
    init_db(db)
    with connect(db) as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='execution_log'"
        ).fetchone()
        if row is None:
            raise RuntimeError("execution_log table missing after init_db")
        idx = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_execution_log_live_dedup'"
        ).fetchone()
        if idx is None:
            conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_execution_log_live_dedup
                ON execution_log (idempotency_key)
                WHERE dry_run = 0 AND status = 'routed'
                """
            )
            conn.commit()
    return db


def live_execution_exists(
    runner_id: str,
    bet_leg: str,
    venue: str,
    *,
    database: Path | None = None,
) -> bool:
    """True if a live routed offer already exists for this runner leg."""
    db = database or db_path(load_config())
    ensure_execution_log_schema(db)
    key = idempotency_key(runner_id, bet_leg, venue)
    with connect(db) as conn:
        row = conn.execute(
            """
            SELECT 1 FROM execution_log
            WHERE idempotency_key = ? AND dry_run = 0 AND status = 'routed'
            LIMIT 1
            """,
            (key,),
        ).fetchone()
    return row is not None


def _result_row(
    result: ExecutionResult,
    *,
    batch_id: str,
    bet_leg: str,
    log_id: str | None = None,
) -> dict[str, Any]:
    intent = result.intent
    venue = result.venue or "none"
    payload = result.payload or {}
    key = idempotency_key(intent.runner_id, bet_leg, venue)
    win_odds = intent.offered_odds or intent.min_odds
    place_odds_val = intent.offered_place_odds or intent.min_place_odds
    leg_odds = place_odds_val if bet_leg == "place" else win_odds
    leg_stake = payload.get("stake") or intent.stake
    return {
        "log_id": log_id or str(uuid.uuid4()),
        "batch_id": batch_id,
        "runner_id": intent.runner_id,
        "race_id": intent.race_id,
        "horse_name": intent.horse_name,
        "course": intent.course,
        "off_time": intent.off_time,
        "bet_type": intent.bet_type,
        "bet_leg": bet_leg,
        "venue": venue,
        "status": result.status,
        "dry_run": 1 if result.dry_run else 0,
        "stake": leg_stake,
        "odds": leg_odds,
        "place_odds": place_odds_val,
        "steam_gate": intent.steam_gate,
        "value_flag": 1 if intent.value_flag else 0,
        "kelly_multiplier": intent.kelly_multiplier,
        "message": result.message,
        "external_id": result.external_id,
        "matchbook_runner_id": payload.get("runner-id") or intent.matchbook_runner_id,
        "matchbook_market_id": payload.get("market-id") or intent.matchbook_market_id,
        "matchbook_place_market_id": intent.matchbook_place_market_id,
        "matchbook_event_id": intent.matchbook_event_id,
        "betfair_market_id": intent.betfair_market_id,
        "betfair_selection_id": intent.betfair_selection_id,
        "betfair_place_market_id": getattr(intent, "betfair_place_market_id", None),
        "payload_json": json.dumps(result.payload, default=str) if result.payload else None,
        "idempotency_key": key,
        "created_at": _utc_now(),
    }


def append_execution_log(
    result: ExecutionResult,
    *,
    batch_id: str,
    bet_leg: str | None = None,
    database: Path | None = None,
) -> str:
    """Persist one routing outcome. Returns log_id."""
    db = database or db_path(load_config())
    ensure_execution_log_schema(db)
    leg = bet_leg or bet_leg_for_intent(result.intent, payload=result.payload)
    row = _result_row(result, batch_id=batch_id, bet_leg=leg)
    cols = ", ".join(row.keys())
    placeholders = ", ".join("?" for _ in row)
    with connect(db) as conn:
        conn.execute(
            f"INSERT INTO execution_log ({cols}) VALUES ({placeholders})",
            tuple(row.values()),
        )
        conn.commit()
    return str(row["log_id"])


def append_execution_batch(
    results: list[ExecutionResult],
    *,
    batch_id: str | None = None,
    database: Path | None = None,
) -> tuple[str, list[str]]:
    """Persist a full routing batch. Returns (batch_id, log_ids)."""
    bid = batch_id or str(uuid.uuid4())
    log_ids: list[str] = []
    for result in results:
        log_ids.append(append_execution_log(result, batch_id=bid, database=database))
    return bid, log_ids


def recent_execution_logs(
    *,
    limit: int = 40,
    batch_id: str | None = None,
    database: Path | None = None,
) -> list[dict[str, Any]]:
    db = database or db_path(load_config())
    ensure_execution_log_schema(db)
    with connect(db) as conn:
        if batch_id:
            rows = conn.execute(
                """
                SELECT * FROM execution_log
                WHERE batch_id = ?
                ORDER BY created_at DESC, log_id
                LIMIT ?
                """,
                (batch_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM execution_log
                ORDER BY created_at DESC, log_id
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
    return [dict(r) for r in rows]


def execution_log_summary(*, database: Path | None = None) -> dict[str, Any]:
    db = database or db_path(load_config())
    ensure_execution_log_schema(db)
    with connect(db) as conn:
        total = conn.execute("SELECT COUNT(*) FROM execution_log").fetchone()[0]
        live_routed = conn.execute(
            "SELECT COUNT(*) FROM execution_log WHERE dry_run = 0 AND status = 'routed'"
        ).fetchone()[0]
        last = conn.execute(
            "SELECT batch_id, created_at FROM execution_log ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        status_rows = conn.execute(
            "SELECT status, COUNT(*) AS n FROM execution_log GROUP BY status ORDER BY n DESC"
        ).fetchall()
    return {
        "total_rows": int(total),
        "live_routed": int(live_routed),
        "last_batch_id": last["batch_id"] if last else None,
        "last_created_at": last["created_at"] if last else None,
        "status_counts": {str(r["status"]): int(r["n"]) for r in status_rows},
    }


def _serialize_log_row(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    out["dry_run"] = bool(out.get("dry_run"))
    out["value_flag"] = bool(out.get("value_flag"))
    return out


def recent_execution_batches(
    *,
    limit: int = 5,
    database: Path | None = None,
) -> list[dict[str, Any]]:
    db = database or db_path(load_config())
    ensure_execution_log_schema(db)
    with connect(db) as conn:
        rows = conn.execute(
            """
            SELECT batch_id,
                   MIN(created_at) AS created_at,
                   COUNT(*) AS rows,
                   SUM(CASE WHEN dry_run = 0 THEN 1 ELSE 0 END) AS live_rows,
                   SUM(CASE WHEN status IN ('routed', 'stub_ok') THEN 1 ELSE 0 END) AS accepted,
                   SUM(CASE WHEN status = 'rejected' THEN 1 ELSE 0 END) AS rejected,
                   SUM(CASE WHEN status = 'skipped_duplicate' THEN 1 ELSE 0 END) AS skipped_duplicate
            FROM execution_log
            GROUP BY batch_id
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def execution_audit_panel(
    *,
    log_limit: int = 30,
    batch_limit: int = 5,
    database: Path | None = None,
) -> dict[str, Any]:
    """Payload for /status routing audit panel and /api/execution/log."""
    db = database or db_path(load_config())
    summary = execution_log_summary(database=db)
    logs = [_serialize_log_row(r) for r in recent_execution_logs(limit=log_limit, database=db)]
    batches = recent_execution_batches(limit=batch_limit, database=db)
    return {
        **summary,
        "recent_batches": batches,
        "recent_logs": logs,
    }


def duplicate_skip_result(
    intent: ExecutionIntent,
    *,
    venue: str,
    dry_run: bool,
    bet_leg: str = "win",
) -> ExecutionResult:
    return ExecutionResult(
        intent=intent,
        venue=venue,
        status="skipped_duplicate",
        dry_run=dry_run,
        message=f"Live {bet_leg} offer already logged for this runner — skipped to prevent double-bet",
        payload={"bet_leg": bet_leg},
    )
