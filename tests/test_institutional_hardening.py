"""Institutional++ hardening — production recon lane and ledger upsert."""

import pandas as pd

from hibs_racing.features.store import init_db
from hibs_racing.institutional.paper_reconciliation import reconcile_paper_ledger
from hibs_racing.place.paper_ledger import record_paper_bet


def test_record_paper_bet_promotes_existing_row_to_value(tmp_path):
    db = tmp_path / "promote.db"
    init_db(db)
    bet_id = record_paper_bet("race1", "r1", "each_way", 1.0, is_value_pick=False, database=db)
    assert bet_id
    bet_id2 = record_paper_bet("race1", "r1", "each_way", 1.0, is_value_pick=True, database=db)
    assert bet_id2 == bet_id
    with __import__("hibs_racing.features.store", fromlist=["connect"]).connect(db) as conn:
        row = conn.execute(
            "SELECT is_value_pick FROM paper_bets WHERE bet_id = ?", (bet_id,)
        ).fetchone()
    assert int(row[0]) == 1


def test_reconcile_historical_uses_production_lane(tmp_path):
    from hibs_racing.backtest.snapshot_store import scoring_config_hash, upsert_snapshots

    db = tmp_path / "recon.db"
    init_db(db)
    frame = pd.DataFrame(
        [
            {
                "runner_id": "r1",
                "race_id": "race1",
                "course": "X",
                "race_name": "Class 4 Handicap",
                "field_size": 10,
                "official_rating": 70,
                "win_decimal": 5.0,
                "place_fraction": 0.25,
                "places": 3,
                "model_score": 0.9,
                "model_win_prob": 0.2,
                "model_place_prob": 0.45,
                "combo_bayes_place": 0.3,
                "place_ev": 0.08,
                "ew_combined_ev": 0.1,
                "flag_raw": 1,
                "jockey": "J",
                "trainer": "T",
                "card_comment": "ok",
            }
        ]
    )
    upsert_snapshots(db, "2026-06-01", frame, finish_by_runner={"r1": 2})
    record_paper_bet("race1", "r1", "each_way", 1.0, is_value_pick=True, database=db)
    with __import__("hibs_racing.features.store", fromlist=["connect"]).connect(db) as conn:
        conn.execute(
            """
            INSERT INTO upcoming_runners (
                runner_id, race_id, card_date, horse_id, horse_name, source, fetched_at,
                win_decimal, place_fraction, places
            ) VALUES ('r1','race1','2026-06-01','h1','H','test','2026-06-01T06:00:00',5,0.25,3)
            """
        )
        conn.commit()
    recon = reconcile_paper_ledger("2026-06-01", database=db)
    assert recon.is_clean
    assert recon.expected_value_picks == 1


def test_model_version_stamp_changes_when_file_mtime_changes(tmp_path):
    import os
    import time

    from hibs_racing.backtest.snapshot_store import _model_version_stamp

    model = tmp_path / "lgbm_ranker.txt"
    model.write_text("v1", encoding="utf-8")
    cfg = {"paths": {"model_dir": str(tmp_path)}, "ranker": {"model_file": "lgbm_ranker.txt"}}
    s1 = _model_version_stamp(cfg)
    time.sleep(1.05)
    os.utime(model, (model.stat().st_mtime + 2, model.stat().st_mtime + 2))
    s2 = _model_version_stamp(cfg)
    assert s1 != s2
