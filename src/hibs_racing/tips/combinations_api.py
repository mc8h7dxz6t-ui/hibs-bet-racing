from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from hibs_racing.tips.group_combinations import group_tips_from_text
from hibs_racing.tips.store import load_email_bodies_for_date, load_tips
from hibs_racing.models.win_engine_insights import attach_win_engine_to_combinations


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
    """Build combination payload — tipster email, DB singles, or engine-suggested combos."""
    target_date = card_date or date.today().isoformat()
    rows = load_tips(db, card_date=target_date, limit=500)
    lookup = _runner_lookup_from_rows(rows)
    bodies = load_email_bodies_for_date(db, target_date)

    combinations: list[dict[str, Any]] = []
    singles: list[dict[str, Any]] = []
    source = "engine"

    if bodies:
        source = "tipster"
        for body in bodies:
            grouped = group_tips_from_text(
                body,
                default_card_date=target_date,
                runner_lookup=lookup,
            )
            combinations.extend(grouped.get("combinations") or [])
            singles.extend(grouped.get("singles") or [])
    elif rows:
        source = "tipster"
        singles = _tips_as_singles(rows)

    if not combinations:
        from hibs_racing.tips.suggested_combinations import build_engine_combinations

        engine_payload = build_engine_combinations()
        engine_combos = engine_payload.get("combinations") or []
        if engine_combos:
            combinations = engine_combos
            if not bodies and not rows:
                source = "engine"
                singles = engine_payload.get("singles") or []
            elif not singles:
                singles = engine_payload.get("singles") or []

    return attach_win_engine_to_combinations(
        {
            "ok": True,
            "card_date": target_date,
            "combinations": combinations,
            "singles": singles,
            "tip_count": len(rows),
            "source": source,
        },
        db,
    )
