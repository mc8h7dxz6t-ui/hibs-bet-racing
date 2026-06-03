"""Shadow execution log — would-have-bet at morning odds (Phase 3 / no live capital)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from hibs_racing.config import db_path, load_config
from hibs_racing.features.store import connect, init_db
from hibs_racing.institutional.contracts import BetIntent, stable_event_id
from hibs_racing.institutional.ledger_events import append_ledger_event


def log_shadow_intents(
    scored: pd.DataFrame,
    *,
    manifest_id: str | None = None,
    venue: str = "shadow",
    strategy_id: str = "HIBS_RACING_PRODUCTION",
    database: Path | None = None,
) -> list[BetIntent]:
    """Record BetIntent-shaped shadow rows for value picks — no broker routing."""
    db = database or db_path(load_config())
    init_db(db)
    ts_ns = int(datetime.now(timezone.utc).timestamp() * 1_000_000_000)
    intents: list[BetIntent] = []
    picks = scored[scored.get("value_flag", 0) == 1] if not scored.empty else scored
    for rec in picks.to_dict(orient="records"):
        intent_id = stable_event_id("shadow", rec["runner_id"], str(ts_ns))
        intent = BetIntent(
            intent_msg_id=intent_id,
            strategy_id=strategy_id,
            venue=venue,
            runner_id=str(rec["runner_id"]),
            race_id=str(rec["race_id"]),
            bet_type="each_way",
            stake_units="1.0",
            offered_win=str(rec.get("win_decimal") or ""),
            model_ev=str(rec.get("ew_combined_ev") or ""),
            timestamp_ns=ts_ns,
        )
        intents.append(intent)
        append_ledger_event(
            event_type="shadow_intent",
            runner_id=intent.runner_id,
            race_id=intent.race_id,
            manifest_id=manifest_id,
            payload={
                "intent_msg_id": intent.intent_msg_id,
                "strategy_id": intent.strategy_id,
                "venue": intent.venue,
                "bet_type": intent.bet_type,
                "stake_units": intent.stake_units,
                "offered_win": intent.offered_win,
                "model_ev": intent.model_ev,
                "card_date": rec.get("card_date"),
            },
            database=db,
        )
    return intents


def shadow_intent_count(card_date: str, database: Path | None = None) -> int:
    db = database or db_path(load_config())
    init_db(db)
    with connect(db) as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) FROM ledger_events
            WHERE event_type = 'shadow_intent'
              AND payload_json LIKE ?
            """,
            (f'%"card_date": "{card_date}"%',),
        ).fetchone()
    return int(row[0]) if row else 0
