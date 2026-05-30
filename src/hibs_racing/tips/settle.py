from __future__ import annotations

import sqlite3

from hibs_racing.config import load_config


def settle_matched_tips(conn: sqlite3.Connection) -> int:
    """Join matched tips to ingested results and record win/place."""
    place_cutoff = load_config().get("backtest", {}).get("place_cutoff_default", 3)
    rows = conn.execute(
        """
        SELECT tip_id, runner_id, race_id, card_date
        FROM tipster_tips
        WHERE match_status IN ('matched', 'ambiguous')
          AND settled_at IS NULL
          AND runner_id IS NOT NULL
        """
    ).fetchall()
    count = 0
    for row in rows:
        result = conn.execute(
            """
            SELECT finish_pos, field_size, sp_decimal
            FROM runners
            WHERE runner_id = ?
            """,
            (row["runner_id"],),
        ).fetchone()
        if not result or result["finish_pos"] is None:
            continue
        finish = int(result["finish_pos"])
        field = int(result["field_size"] or place_cutoff)
        effective = min(place_cutoff, field)
        won = 1 if finish == 1 else 0
        placed = 1 if finish <= effective else 0
        from hibs_racing.tips.store import update_tip_settlement

        update_tip_settlement(
            conn,
            row["tip_id"],
            finish_pos=finish,
            won=won,
            placed=placed,
            result_sp=result["sp_decimal"],
        )
        count += 1
    return count
