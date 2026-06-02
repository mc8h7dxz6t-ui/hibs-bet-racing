"""Append-only ledger events — institutional audit trail."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hibs_racing.config import db_path, load_config
from hibs_racing.features.store import connect, init_db
from hibs_racing.institutional.contracts import LedgerEvent, stable_event_id


def append_ledger_event(
    *,
    event_type: str,
    payload: dict[str, Any],
    runner_id: str | None = None,
    race_id: str | None = None,
    manifest_id: str | None = None,
    verification_hash: str | None = None,
    database: Path | None = None,
) -> LedgerEvent:
    db = database or db_path(load_config())
    init_db(db)
    created = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    payload_json = json.dumps(payload, sort_keys=True, default=str)
    event_id = stable_event_id(event_type, runner_id or "", race_id or "", created, payload_json[:64])
    event = LedgerEvent(
        event_id=event_id,
        event_type=event_type,
        runner_id=runner_id,
        race_id=race_id,
        payload_json=payload_json,
        manifest_id=manifest_id,
        verification_hash=verification_hash,
        created_at=created,
    )
    with connect(db) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO ledger_events (
                event_id, event_type, runner_id, race_id,
                payload_json, manifest_id, verification_hash, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.event_id,
                event.event_type,
                event.runner_id,
                event.race_id,
                event.payload_json,
                event.manifest_id,
                event.verification_hash,
                event.created_at,
            ),
        )
        conn.commit()
    return event


def list_ledger_events(
    *,
    event_type: str | None = None,
    card_date: str | None = None,
    limit: int = 100,
    database: Path | None = None,
) -> list[dict[str, Any]]:
    db = database or db_path(load_config())
    init_db(db)
    clauses = ["1=1"]
    params: list[Any] = []
    if event_type:
        clauses.append("event_type = ?")
        params.append(event_type)
    if card_date:
        clauses.append("payload_json LIKE ?")
        params.append(f'%"card_date": "{card_date}"%')
    params.append(limit)
    sql = f"""
        SELECT event_id, event_type, runner_id, race_id, payload_json,
               manifest_id, verification_hash, created_at
        FROM ledger_events
        WHERE {' AND '.join(clauses)}
        ORDER BY created_at DESC
        LIMIT ?
    """
    with connect(db) as conn:
        rows = conn.execute(sql, params).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        out.append(
            {
                "event_id": row[0],
                "event_type": row[1],
                "runner_id": row[2],
                "race_id": row[3],
                "payload": json.loads(row[4]) if row[4] else {},
                "manifest_id": row[5],
                "verification_hash": row[6],
                "created_at": row[7],
            }
        )
    return out
