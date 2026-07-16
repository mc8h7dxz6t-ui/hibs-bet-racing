from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from hibs_racing.tips.group_combinations import group_tips_from_text
from hibs_racing.tips.store import load_email_bodies_for_date, load_tips


def _runner_lookup_from_rows(rows: list[dict[str, Any]]) -> dict[tuple, str | None]:
    lookup: dict[tuple, str | None] = {}
    for row in rows:
        key = (
            row.get("horse_name"),
            row.get("course"),
            row.get("off_time"),
            row.get("card_date"),
        )
        lookup[key] = row.get("runner_id")
    return lookup


def _tips_as_singles(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    singles: list[dict[str, Any]] = []
    for row in rows:
        event_parts = [p for p in (row.get("course"), row.get("off_time")) if p]
        singles.append(
            {
                "event": " ".join(event_parts) if event_parts else "—",
                "selection": row.get("horse_name") or "—",
                "market": row.get("bet_type") or "win",
                "odds_decimal": row.get("odds_decimal"),
                "runner_id": row.get("runner_id"),
            }
        )
    return singles


def combinations_for_date(db: Path, card_date: str | None = None) -> dict[str, Any]:
    """Build combination payload for API — re-parse stored bodies or fall back to DB singles."""
    target_date = card_date or date.today().isoformat()
    rows = load_tips(db, card_date=target_date, limit=500)
    lookup = _runner_lookup_from_rows(rows)
    bodies = load_email_bodies_for_date(db, target_date)

    combinations: list[dict[str, Any]] = []
    singles: list[dict[str, Any]] = []

    if bodies:
        for body in bodies:
            grouped = group_tips_from_text(
                body,
                default_card_date=target_date,
                runner_lookup=lookup,
            )
            combinations.extend(grouped.get("combinations") or [])
            singles.extend(grouped.get("singles") or [])
    elif rows:
        singles = _tips_as_singles(rows)

    return {
        "ok": True,
        "card_date": target_date,
        "combinations": combinations,
        "singles": singles,
        "tip_count": len(rows),
    }
