import json

import pandas as pd
import pytest

from hibs_racing.cards.score_card import score_upcoming_cards
from hibs_racing.config import ranker_feature_path, ranker_model_path
from hibs_racing.features.ranker_matrix import build_card_feature_frame, build_ranker_matrix, ranker_feature_columns
from hibs_racing.features.store import connect, init_db
from hibs_racing.models.lgbm_ranker import load_ranker, train_lgbm_ranker


def _seed_history(db):
    rows = []
    for race_idx in range(60):
        race_id = f"hist_r{race_idx}"
        race_date = f"2026-04-{1 + (race_idx % 28):02d}"
        for horse_idx in range(4):
            finish = horse_idx + 1
            runner_id = f"{race_id}:h{horse_idx}"
            rows.append(
                (
                    runner_id,
                    race_id,
                    race_date,
                    f"H{race_idx}_{horse_idx}",
                    f"J{horse_idx % 2}",
                    f"T{horse_idx % 2}",
                    horse_idx + 1,
                    70 + horse_idx,
                    72 + horse_idx,
                    "Class 4",
                    10,
                    finish,
                    4,
                    0.5,
                    1,
                    0,
                )
            )
    with connect(db) as conn:
        for row in rows:
            conn.execute(
                """
                INSERT INTO runners (
                    runner_id, race_id, race_date, horse_id, jockey, trainer, draw,
                    official_rating, rpr, race_class, days_since_last_run, finish_pos,
                    field_size, comment_raw, comment_norm, ingested_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ok', 'ok', 'now')
                """,
                row[:13],
            )
            conn.execute(
                """
                INSERT INTO comment_tags (
                    runner_id, sectional_composite, finishing_burst_level, late_pace_level, tagged_at
                ) VALUES (?, ?, ?, ?, 'now')
                """,
                (row[0], row[13], row[14], row[15]),
            )
        conn.commit()


def _lightgbm_works() -> bool:
    try:
        import lightgbm  # noqa: F401
        return True
    except (ImportError, OSError):
        return False


def test_build_card_feature_frame_pit_combo(tmp_path, monkeypatch):
    db = tmp_path / "t.sqlite"
    monkeypatch.setenv("HIBS_RACING_DB_PATH", str(db))
    init_db(db)
    _seed_history(db)

    cards = pd.DataFrame(
        [
            {
                "runner_id": "R1:horse_a",
                "race_id": "R1",
                "card_date": "2026-05-30",
                "horse_id": "H0",
                "horse_name": "Horse A",
                "jockey": "J0",
                "trainer": "T0",
                "official_rating": 70,
                "rpr": 75,
                "race_class": "Class 4",
                "field_size": 2,
                "card_comment": "held up, headway 2f out",
            }
        ]
    )
    frame = build_card_feature_frame(cards, database=db)
    assert len(frame) == 1
    for col in ranker_feature_columns():
        assert col in frame.columns


def test_score_card_heuristic_when_no_model(tmp_path, monkeypatch):
    monkeypatch.setattr("hibs_racing.config.ROOT", tmp_path)
    cfg_dir = tmp_path / "ingest"
    cfg_dir.mkdir()
    (cfg_dir / "config.yaml").write_text(
        """
paths:
  db_path: data/feature_store.sqlite
  parquet_dir: data/parquet
  model_dir: models
ranker:
  scoring_mode: auto
  model_file: lgbm_ranker.txt
  feature_file: lgbm_ranker_features.json
backtest:
  train_end: "2026-04-30"
  test_start: "2026-05-01"
""",
        encoding="utf-8",
    )
    db = tmp_path / "data" / "feature_store.sqlite"
    db.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HIBS_RACING_DB_PATH", str(db))
    init_db(db)

    cards = pd.DataFrame(
        [
            {
                "runner_id": "R1:horse_a",
                "race_id": "R1",
                "card_date": "2026-05-30",
                "horse_id": "Horse A",
                "horse_name": "Horse A",
                "jockey": "J1",
                "trainer": "T1",
                "official_rating": 70,
                "rpr": 75,
                "race_class": "Class 4",
                "field_size": 2,
                "card_comment": "held up, headway 2f out",
            },
            {
                "runner_id": "R1:horse_b",
                "race_id": "R1",
                "card_date": "2026-05-30",
                "horse_id": "Horse B",
                "horse_name": "Horse B",
                "jockey": "J2",
                "trainer": "T2",
                "official_rating": 80,
                "rpr": 82,
                "race_class": "Class 4",
                "field_size": 2,
                "card_comment": "",
            },
        ]
    )
    scored = score_upcoming_cards(cards, database=db)
    assert len(scored) == 2
    assert scored.iloc[0]["scoring_method"] == "heuristic"
    assert "Model artifacts missing" in str(scored.iloc[0].get("scoring_fallback_reason", ""))


@pytest.mark.skipif(not _lightgbm_works(), reason="lightgbm not installed or libomp missing")
def test_score_card_uses_ranker_when_model_exists(tmp_path, monkeypatch):
    monkeypatch.setattr("hibs_racing.config.ROOT", tmp_path)
    cfg_dir = tmp_path / "ingest"
    cfg_dir.mkdir()
    (cfg_dir / "config.yaml").write_text(
        """
paths:
  db_path: data/feature_store.sqlite
  parquet_dir: data/parquet
  model_dir: models
ranker:
  combo_alpha: 8.0
  min_rows: 50
  min_races: 10
  model_file: lgbm_ranker.txt
  feature_file: lgbm_ranker_features.json
  scoring_mode: auto
backtest:
  train_end: "2026-04-15"
  test_start: "2026-04-16"
  place_cutoff_default: 3
""",
        encoding="utf-8",
    )

    from hibs_racing.config import load_config

    cfg = load_config(cfg_dir / "config.yaml")
    db = tmp_path / cfg["paths"]["db_path"]
    db.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HIBS_RACING_DB_PATH", str(db))
    init_db(db)
    _seed_history(db)

    matrix = build_ranker_matrix(database=db, config_path=cfg_dir / "config.yaml", export_parquet=False)
    report = train_lgbm_ranker(matrix, config_path=cfg_dir / "config.yaml", min_rows=50, min_races=10)
    assert report.model_path is not None
    assert load_ranker(ranker_model_path(cfg)) is not None

    cards = pd.DataFrame(
        [
            {
                "runner_id": "R1:horse_a",
                "race_id": "R1",
                "card_date": "2026-05-30",
                "horse_id": "H0",
                "horse_name": "Horse A",
                "jockey": "J0",
                "trainer": "T0",
                "official_rating": 70,
                "rpr": 75,
                "race_class": "Class 4",
                "field_size": 2,
            },
            {
                "runner_id": "R1:horse_b",
                "race_id": "R1",
                "card_date": "2026-05-30",
                "horse_id": "H1",
                "horse_name": "Horse B",
                "jockey": "J1",
                "trainer": "T1",
                "official_rating": 80,
                "rpr": 82,
                "race_class": "Class 4",
                "field_size": 2,
            },
        ]
    )
    scored = score_upcoming_cards(cards, database=db)
    assert scored.iloc[0]["scoring_method"] == "ranker"
    assert "model_place_prob" in scored.columns

    features = json.loads(ranker_feature_path(cfg).read_text(encoding="utf-8"))["features"]
    assert features == [c for c in ranker_feature_columns() if c in matrix.columns]
