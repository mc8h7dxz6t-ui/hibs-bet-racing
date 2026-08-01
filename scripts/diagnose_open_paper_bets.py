#!/usr/bin/env python3
"""Report why open paper bets are not settling — missing IRE results vs name/key mismatch."""
from __future__ import annotations

import json
import sys
from collections import Counter

from hibs_racing.config import db_path, load_config
from hibs_racing.entity.natural_key import generate_natural_key
from hibs_racing.features.store import connect, init_db
from hibs_racing.place.paper_ledger import _find_finish_pos, _resolve_bet_context


def main() -> int:
    cfg = load_config()
    db = db_path(cfg)
    init_db(db)
    with connect(db) as conn:
        open_rows = conn.execute(
            """
            SELECT bet_id, race_id, runner_id, card_date, course, off_time,
                   horse_name, race_natural_key, created_at
            FROM paper_bets WHERE status = 'open' AND backtest = 0
            ORDER BY created_at DESC
            """
        ).fetchall()

    by_course: Counter[str] = Counter()
    by_reason: Counter[str] = Counter()
    samples: list[dict] = []
    results_by_course: dict[str, int] = {}

    with connect(db) as conn:
        for row in open_rows:
            bet_id, race_id, runner_id, card_date, course, off_time, horse_name, rnk, created_at = row
            course_s = str(course or "unknown")
            by_course[course_s] += 1
            ctx = _resolve_bet_context(
                conn,
                race_id=race_id,
                runner_id=runner_id,
                card_date=card_date,
                horse_name=horse_name,
                course=course,
                off_time=off_time,
                race_natural_key=rnk,
                created_at=created_at,
            )
            cd = ctx.get("card_date")
            if not cd:
                by_reason["no_card_date"] += 1
                continue
            if course_s not in results_by_course:
                n = conn.execute(
                    """
                    SELECT COUNT(*) FROM runners
                    WHERE race_date = ? AND finish_pos IS NOT NULL
                      AND lower(course) LIKE ?
                    """,
                    (cd, f"%{course_s.lower().split()[0]}%"),
                ).fetchone()[0]
                results_by_course[course_s] = int(n or 0)

            pos = _find_finish_pos(
                conn,
                race_id=race_id,
                card_date=cd,
                horse_name=ctx.get("horse_name"),
                runner_id=runner_id,
                course=ctx.get("course"),
                off_time=ctx.get("off_time"),
                race_natural_key=ctx.get("race_natural_key"),
            )
            if pos is not None:
                by_reason["would_settle"] += 1
            elif results_by_course.get(course_s, 0) == 0:
                by_reason["no_results_for_course_date"] += 1
                if len(samples) < 8:
                    samples.append(
                        {
                            "bet_id": bet_id,
                            "card_date": cd,
                            "course": course_s,
                            "horse_name": ctx.get("horse_name"),
                            "hint": "run: hibs-racing scrape --region ire --type flat --days 14 --ingest",
                        }
                    )
            else:
                by_reason["results_exist_but_no_match"] += 1
                if len(samples) < 8:
                    nk = generate_natural_key(cd, ctx.get("course"), ctx.get("off_time"))
                    samples.append(
                        {
                            "bet_id": bet_id,
                            "card_date": cd,
                            "course": course_s,
                            "horse_name": ctx.get("horse_name"),
                            "natural_key": nk,
                            "stored_key": ctx.get("race_natural_key"),
                        }
                    )

    out = {
        "open_bets": len(open_rows),
        "by_course": dict(by_course.most_common(15)),
        "by_reason": dict(by_reason),
        "results_rows_by_course": results_by_course,
        "samples": samples,
    }
    print(json.dumps(out, indent=2))
    return 0 if not open_rows else 1


if __name__ == "__main__":
    sys.exit(main())
