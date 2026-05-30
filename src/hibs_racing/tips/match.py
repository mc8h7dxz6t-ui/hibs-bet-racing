from __future__ import annotations

import re
import sqlite3

from hibs_racing.entity.natural_key import courses_match, normalize_off_time


def _norm_horse(name: str | None) -> str:
    if not name:
        return ""
    text = name.lower().strip()
    text = re.sub(r"[^a-z0-9\s]", "", text)
    return re.sub(r"\s+", " ", text)


def _horse_match(a: str | None, b: str | None) -> bool:
    na, nb = _norm_horse(a), _norm_horse(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    return na in nb or nb in na


def _time_match(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return True
    return normalize_off_time(a) == normalize_off_time(b)


def match_tip_to_runners(
    conn: sqlite3.Connection,
    *,
    card_date: str | None,
    horse_name: str | None,
    course: str | None,
    off_time: str | None,
) -> tuple[str | None, str | None, str]:
    """
    Match tip to runners (results) or upcoming_runners (cards).
    Returns (runner_id, race_id, status).
    """
    if not card_date:
        return None, None, "unmatched"

    candidates: list[sqlite3.Row] = []

    for table in ("runners", "upcoming_runners"):
        date_col = "race_date" if table == "runners" else "card_date"
        horse_col = "horse_id" if table == "runners" else "horse_name"
        rows = conn.execute(
            f"""
            SELECT runner_id, race_id, {horse_col} AS horse_name, course, off_time
            FROM {table}
            WHERE {date_col} = ?
            """,
            (card_date,),
        ).fetchall()
        candidates.extend(rows)

    if not candidates:
        return None, None, "unmatched"

    filtered = [
        r
        for r in candidates
        if (not course or courses_match(r["course"], course))
        and _time_match(off_time, r["off_time"])
    ]
    if horse_name:
        filtered = [r for r in filtered if _horse_match(horse_name, r["horse_name"])]

    if len(filtered) == 1:
        row = filtered[0]
        return row["runner_id"], row["race_id"], "matched"
    if len(filtered) > 1:
        row = filtered[0]
        return row["runner_id"], row["race_id"], "ambiguous"
    return None, None, "unmatched"
