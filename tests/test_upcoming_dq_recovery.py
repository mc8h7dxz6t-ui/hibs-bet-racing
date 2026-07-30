"""Tests for upcoming-card DQ recovery."""

from __future__ import annotations

import pandas as pd


def test_derive_raceform_enrich_sets_course_rate(tmp_path, monkeypatch):
    from hibs_racing.cards.upcoming_dq_recovery import derive_raceform_enrich_for_upcoming
    from hibs_racing.config import db_path, load_config
    from hibs_racing.features.store import connect, init_db

    cfg = load_config()
    db = tmp_path / "raceform.db"
    monkeypatch.setattr("hibs_racing.cards.upcoming_dq_recovery.db_path", lambda _cfg=None: db)

    init_db(db)
    with connect(db) as conn:
        conn.executemany(
            """
            INSERT INTO runners (
                runner_id, race_id, race_date, horse_id, course, finish_pos,
                comment_raw, comment_norm, ingested_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'x', 'x', 'now')
            """,
            [
                ("h1", "r1", "2026-07-01", "horse_a", "Goodwood", 1),
                ("h2", "r2", "2026-07-10", "horse_a", "Goodwood", 3),
                ("h3", "r3", "2026-07-12", "horse_a", "Goodwood", 2),
            ],
        )
        conn.commit()

    frame = pd.DataFrame(
        [
            {
                "runner_id": "u1",
                "horse_id": "horse_a",
                "course": "Goodwood",
                "card_date": "2026-07-30",
            }
        ]
    )
    out, meta = derive_raceform_enrich_for_upcoming(frame)
    assert meta["updated"] == 1
    assert out.iloc[0]["enrich_source"] == "raceform_derived"
    assert float(out.iloc[0]["horse_course_win_rate"]) > 0


def test_repair_upcoming_dense_fields_from_rp_json(tmp_path, monkeypatch):
    from hibs_racing.cards.upcoming_dq_recovery import repair_upcoming_dense_fields
    from hibs_racing.ingest.racecards import RPSCRAPE_RACECARDS

    cards_dir = tmp_path / "racecards"
    cards_dir.mkdir()
    monkeypatch.setattr("hibs_racing.cards.upcoming_dq_recovery.RPSCRAPE_RACECARDS", cards_dir)
    monkeypatch.setattr("hibs_racing.ingest.dense_field_repair.RPSCRAPE_RACECARDS", cards_dir)

    card_date = "2026-07-30"
    payload = {
        "GB": {
            "Goodwood": {
                "14:30": {
                    "race_id": "race1",
                    "date": card_date,
                    "course": "Goodwood",
                    "race_name": "Handicap",
                    "runners": [
                        {
                            "name": "Cannes",
                            "horse_id": "h1",
                            "ofr": 88,
                            "comment": "held up",
                            "trainer_rtf": "22%",
                            "form": "112",
                        }
                    ],
                }
            }
        }
    }
    import json

    (cards_dir / f"{card_date}.json").write_text(json.dumps(payload), encoding="utf-8")

    frame = pd.DataFrame(
        [
            {
                "runner_id": "u1",
                "horse_id": "h1",
                "horse_name": "Cannes",
                "course": "Goodwood",
                "card_date": card_date,
                "off_time": "14:30",
                "race_name": "Handicap",
                "jockey": "A",
                "trainer": "B",
                "win_decimal": 5.0,
                "model_win_prob": 0.1,
                "model_place_prob": 0.3,
            }
        ]
    )
    out, meta = repair_upcoming_dense_fields(frame)
    assert meta["updated"] == 1
    row = out.iloc[0]
    assert int(row["official_rating"]) == 88
    assert row["card_comment"] == "held up"
    assert row["enrich_source"] == "rp_dense_field_repair"


def test_runner_dq_reaches_90_with_enrich_and_handicap():
    from hibs_racing.cards.data_quality import runner_data_quality_pct

    pct = runner_data_quality_pct(
        {
            "race_name": "Class 4 Handicap",
            "win_decimal": 5.0,
            "model_win_prob": 0.1,
            "model_place_prob": 0.3,
            "jockey": "A",
            "trainer": "B",
            "official_rating": 88,
            "card_comment": "held up",
            "enrich_source": "raceform_derived",
            "horse_course_win_rate": 0.2,
            "trainer_rtf": 18,
        }
    )
    assert pct >= 90
