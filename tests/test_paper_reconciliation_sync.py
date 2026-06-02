import pandas as pd

from hibs_racing.features.store import init_db
from hibs_racing.institutional.paper_reconciliation import sync_paper_ledger_to_scored
from hibs_racing.place.paper_ledger import record_paper_bet


def test_sync_paper_ledger_prunes_extras(tmp_path):
    db = tmp_path / "sync.db"
    init_db(db)
    with __import__("hibs_racing.features.store", fromlist=["connect"]).connect(db) as conn:
        conn.execute(
            """
            INSERT INTO upcoming_runners (
                runner_id, race_id, card_date, horse_id, horse_name, source, fetched_at,
                win_decimal, place_fraction, places
            ) VALUES ('r1','race1','2026-06-01','h1','A','test','2026-06-01T06:00:00','5',0.25,3),
                     ('r2','race1','2026-06-01','h2','B','test','2026-06-01T06:00:00','8',0.25,3)
            """
        )
        conn.commit()
    record_paper_bet("race1", "r1", "each_way", 1.0, is_value_pick=True, database=db)
    record_paper_bet("race1", "r2", "each_way", 1.0, is_value_pick=True, database=db)

    scored = pd.DataFrame(
        [
            {"runner_id": "r1", "race_id": "race1", "card_date": "2026-06-01", "value_flag": 1},
            {"runner_id": "r2", "race_id": "race1", "card_date": "2026-06-01", "value_flag": 0},
        ]
    )
    result = sync_paper_ledger_to_scored(scored, card_date="2026-06-01", database=db)
    assert result.is_clean
    assert result.expected_value_picks == 1
    assert result.ledger_value_picks == 1
