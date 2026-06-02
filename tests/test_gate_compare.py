from hibs_racing.backtest.gate_compare import compare_value_gates
from hibs_racing.features.store import connect, init_db


def test_compare_value_gates_counts(tmp_path):
    db = tmp_path / "test.sqlite"
    init_db(db)
    with connect(db) as conn:
        conn.execute(
            """
            INSERT INTO upcoming_runners (
                runner_id, race_id, card_date, race_name, official_rating,
                horse_distance_runs, horse_distance_wins, form_trip_change_f, horse_id, source, fetched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "r1",
                "race1",
                "2026-06-01",
                "Class 4 Handicap",
                70,
                4,
                0,
                3.0,
                "h1",
                "test",
                "2026-06-01T00:00:00+00:00",
            ),
        )
        conn.execute(
            """
            INSERT INTO upcoming_runners (
                runner_id, race_id, card_date, race_name, official_rating, horse_id, source, fetched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "r2",
                "race1",
                "2026-06-01",
                "Class 4 Handicap",
                72,
                "h2",
                "test",
                "2026-06-01T00:00:00+00:00",
            ),
        )
        conn.execute(
            """
            INSERT INTO card_scores (
                runner_id, race_id, model_score, place_ev, combo_bayes_place, value_flag, scored_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("r1", "race1", 0.5, 0.30, 0.5, 0, "2026-06-01T00:00:00+00:00"),
        )
        conn.execute(
            """
            INSERT INTO card_scores (
                runner_id, race_id, model_score, place_ev, combo_bayes_place, value_flag, scored_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("r2", "race1", 0.5, 0.30, 0.5, 0, "2026-06-01T00:00:00+00:00"),
        )
        conn.commit()

    report = compare_value_gates(days=7, database=db)

    assert report.rows == 2
    assert report.raw_value_flags == 2
    assert report.gated_value_flags == 1
    assert report.blocked_by_gates == 1
    assert report.reason_counts.get("poor_distance_record") == 1
