from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from hibs_racing.config import db_path, load_config
from hibs_racing.features.store import connect, init_db
from hibs_racing.nlp.pipeline import parse_comment


def build_tags(
    database: Path | None = None,
    *,
    config_path: Path | None = None,
    use_spacy: bool = False,
) -> dict[str, int]:
    cfg = load_config(config_path)
    db = database or db_path(cfg)
    init_db(db)
    tagged_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    stats = {"tagged": 0, "empty_comment": 0, "sectional_high_pace": 0}
    with connect(db) as conn:
        rows = conn.execute(
            """
            SELECT runner_id, comment_norm, race_type
            FROM runners
            WHERE comment_norm IS NOT NULL AND length(comment_norm) > 0
            """
        ).fetchall()

        for row in rows:
            features = parse_comment(
                row["comment_norm"],
                race_type=row["race_type"],
                use_spacy=use_spacy,
            )
            if features.tag_count == 0:
                stats["empty_comment"] += 1
            if features.late_pace_level >= 3:
                stats["sectional_high_pace"] += 1
            conn.execute(
                """
                INSERT INTO comment_tags (
                    runner_id, late_pace_acceleration, finishing_burst,
                    stamina_deficit, trouble_in_running, prominent_early,
                    held_up, late_pace_level, finishing_burst_level,
                    stamina_deficit_flag, headway_at_furlongs,
                    fade_in_final_furlong, quickened_to_lead,
                    sectional_composite, parser_backend,
                    tag_count, tagged_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(runner_id) DO UPDATE SET
                    late_pace_acceleration = excluded.late_pace_acceleration,
                    finishing_burst = excluded.finishing_burst,
                    stamina_deficit = excluded.stamina_deficit,
                    trouble_in_running = excluded.trouble_in_running,
                    prominent_early = excluded.prominent_early,
                    held_up = excluded.held_up,
                    late_pace_level = excluded.late_pace_level,
                    finishing_burst_level = excluded.finishing_burst_level,
                    stamina_deficit_flag = excluded.stamina_deficit_flag,
                    headway_at_furlongs = excluded.headway_at_furlongs,
                    fade_in_final_furlong = excluded.fade_in_final_furlong,
                    quickened_to_lead = excluded.quickened_to_lead,
                    sectional_composite = excluded.sectional_composite,
                    parser_backend = excluded.parser_backend,
                    tag_count = excluded.tag_count,
                    tagged_at = excluded.tagged_at
                """,
                (
                    row["runner_id"],
                    features.late_pace_acceleration,
                    features.finishing_burst,
                    features.stamina_deficit,
                    features.trouble_in_running,
                    features.prominent_early,
                    features.held_up,
                    features.late_pace_level,
                    features.finishing_burst_level,
                    int(features.stamina_deficit_flag),
                    features.headway_at_furlongs,
                    int(features.fade_in_final_furlong),
                    int(features.quickened_to_lead),
                    features.sectional_composite,
                    features.parser_backend,
                    features.tag_count,
                    tagged_at,
                ),
            )
            stats["tagged"] += 1
        conn.commit()

    return stats


def build_next_run_outcomes(
    database: Path | None = None,
    *,
    config_path: Path | None = None,
    place_cutoff: int | None = None,
) -> int:
    """Join each run to the horse's next race for place/top-N backtest labels."""
    cfg = load_config(config_path)
    db = database or db_path(cfg)
    cutoff = place_cutoff or cfg["backtest"].get("place_cutoff_default", 3)
    init_db(db)
    tagged_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    count = 0

    with connect(db) as conn:
        horses = conn.execute(
            "SELECT DISTINCT horse_id FROM runners WHERE horse_id IS NOT NULL"
        ).fetchall()
        for (horse_id,) in horses:
            runs = conn.execute(
                """
                SELECT runner_id, race_id, race_date, finish_pos, field_size
                FROM runners
                WHERE horse_id = ?
                ORDER BY race_date, race_id
                """,
                (horse_id,),
            ).fetchall()
            for i, run in enumerate(runs[:-1]):
                nxt = runs[i + 1]
                fs = nxt["field_size"] or cutoff
                effective_cutoff = min(cutoff, int(fs))
                placed = (
                    1
                    if nxt["finish_pos"] is not None
                    and int(nxt["finish_pos"]) <= effective_cutoff
                    else 0
                )
                conn.execute(
                    """
                    INSERT INTO next_run_outcomes (
                        runner_id, next_race_id, next_race_date,
                        next_finish_pos, next_placed, place_cutoff, tagged_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(runner_id) DO UPDATE SET
                        next_race_id = excluded.next_race_id,
                        next_race_date = excluded.next_race_date,
                        next_finish_pos = excluded.next_finish_pos,
                        next_placed = excluded.next_placed,
                        place_cutoff = excluded.place_cutoff,
                        tagged_at = excluded.tagged_at
                    """,
                    (
                        run["runner_id"],
                        nxt["race_id"],
                        nxt["race_date"],
                        nxt["finish_pos"],
                        placed,
                        effective_cutoff,
                        tagged_at,
                    ),
                )
                count += 1
        conn.commit()
    return count
