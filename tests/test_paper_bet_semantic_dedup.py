"""Semantic dedupe when API race_id/runner_id churn between refresh-cards runs."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from hibs_racing.features.store import init_db
from hibs_racing.place.paper_ledger import record_paper_bet


def test_record_paper_bet_dedupes_across_race_id_churn(tmp_path: Path) -> None:
    db = tmp_path / "feature_store.sqlite"
    init_db(db)
    a = record_paper_bet(
        "api-race-v1",
        "api-race-v1:goldilocks_cen",
        "each_way",
        1.0,
        offered_win=44.0,
        is_value_pick=True,
        card_date="2026-07-30",
        course="Galway",
        off_time="17:10",
        horse_name="Goldilocks Cen",
        database=db,
    )
    b = record_paper_bet(
        "api-race-v2",
        "api-race-v2:goldilocks_cen",
        "each_way",
        1.0,
        offered_win=44.0,
        is_value_pick=True,
        card_date="2026-07-30",
        course="Galway",
        off_time="17:10",
        horse_name="Goldilocks Cen",
        database=db,
    )
    assert a == b
    with sqlite3.connect(db) as conn:
        n = conn.execute("SELECT COUNT(*) FROM paper_bets").fetchone()[0]
    assert n == 1
