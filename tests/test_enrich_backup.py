from hibs_racing.features.store import connect, init_db
from hibs_racing.ingest import historical_racecards
from hibs_racing.ingest.enrich_backup import derive_enrich_for_date, fetch_racecards_with_fallback


def _seed_runners(db):
    init_db(db)
    with connect(db) as conn:
        conn.executemany(
            """
            INSERT INTO runners (
                runner_id, race_id, race_date, horse_id, course, going, distance_f,
                jockey, trainer, finish_pos, comment_raw, comment_norm, ingested_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'x', 'x', 'now')
            """,
            [
                ("r1", "race_a", "2025-10-01", "h1", "Haydock", "Good", 8.0, "J A", "T A", 1),
                ("r2", "race_a", "2025-10-01", "h2", "Haydock", "Good", 8.0, "J B", "T A", 4),
                ("r3", "race_b", "2025-10-15", "h1", "Haydock", "Soft", 8.0, "J A", "T A", 2),
                ("r4", "race_c", "2025-11-01", "h1", "Haydock", "Good", 8.0, "J A", "T A", 1),
                ("r5", "race_c", "2025-11-01", "h3", "Haydock", "Good", 8.0, "J C", "T B", 5),
            ],
        )
        conn.commit()


def test_derive_enrich_point_in_time(tmp_path):
    db = tmp_path / "t.sqlite"
    _seed_runners(db)
    result = derive_enrich_for_date("2025-11-01", database=db)
    assert result["rows_updated"] == 2
    with connect(db) as conn:
        row = conn.execute(
            "SELECT enrich_source, horse_course_win_rate, form_lto_position FROM runners WHERE runner_id = 'r4'"
        ).fetchone()
    assert row[0] == "raceform_derived"
    assert row[1] == 0.5  # h1: 1 win from 2 prior Haydock runs
    assert row[2] == 2  # LTO at Haydock Soft


def test_fetch_cascade_uses_derived_on_api_failure(tmp_path, monkeypatch):
    db = tmp_path / "t.sqlite"
    _seed_runners(db)

    def _boom(_date):
        raise RuntimeError("RP down")

    monkeypatch.setattr(historical_racecards, "fetch_historical_racecards_on_date", _boom)
    out = fetch_racecards_with_fallback(
        "2025-11-01",
        skip_cached=False,
        use_derived_on_failure=True,
        database=db,
    )
    assert out["source"] == "raceform_derived"
    assert out["rows_backfilled"] == 2
    assert any(s.get("stage") == "raceform_derived" for s in out["stages"])
