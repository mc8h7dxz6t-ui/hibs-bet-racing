import json

import pandas as pd
import pytest

from hibs_racing.features.ranker_matrix import (
    RankerMatrixValidationError,
    build_ranker_matrix,
    impute_enrich_features,
    ranker_enrich_feature_columns,
    validate_ranker_matrix,
)
from hibs_racing.features.runner_enrich_backfill import backfill_runner_enrich
from hibs_racing.features.store import connect, init_db
from hibs_racing.models.ranker_manifest import compute_stable_hash, write_ranker_manifest


def _seed_runner(db, *, enrich: dict | None = None):
    row = {
        "runner_id": "r1:h1",
        "race_id": "r1",
        "race_date": "2026-04-01",
        "horse_id": "Horse One",
        "jockey": "J1",
        "trainer": "T1",
        "draw": 1,
        "official_rating": 70,
        "rpr": 72,
        "race_class": "Class 4",
        "days_since_last_run": 10,
        "finish_pos": 1,
        "field_size": 4,
        "comment_raw": "held up",
        "comment_norm": "held up",
        "ingested_at": "now",
        "course": "Ascot",
        "off_time": "14:30",
    }
    if enrich:
        row.update(enrich)
    cols = list(row.keys())
    placeholders = ", ".join("?" for _ in cols)
    with connect(db) as conn:
        conn.execute(
            f"INSERT INTO runners ({', '.join(cols)}) VALUES ({placeholders})",
            [row[c] for c in cols],
        )
        conn.execute(
            """
            INSERT INTO comment_tags (
                runner_id, sectional_composite, finishing_burst_level, late_pace_level, tagged_at
            ) VALUES (?, 0.5, 1, 0, 'now')
            """,
            (row["runner_id"],),
        )
        conn.commit()


def test_runner_enrich_migrations_apply(tmp_path, monkeypatch):
    db = tmp_path / "t.sqlite"
    monkeypatch.setenv("HIBS_RACING_DB_PATH", str(db))
    init_db(db)
    with connect(db) as conn:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(runners)").fetchall()}
    assert "trainer_rtf" in cols
    assert "form_string" in cols


def test_validate_ranker_matrix_rejects_silent_downgrade():
    frame = pd.DataFrame({"official_rating": [70], "rpr": [72]})
    with pytest.raises(RankerMatrixValidationError, match="Feature count mismatch"):
        validate_ranker_matrix(
            frame,
            with_enrich=True,
            feature_cols=ranker_enrich_feature_columns(),
        )


def test_build_ranker_matrix_with_enrich_compiles_48_features(tmp_path, monkeypatch):
    db = tmp_path / "t.sqlite"
    monkeypatch.setenv("HIBS_RACING_DB_PATH", str(db))
    cfg_dir = tmp_path / "ingest"
    cfg_dir.mkdir()
    (cfg_dir / "config.yaml").write_text(
        """
paths:
  db_path: data/feature_store.sqlite
  parquet_dir: data/parquet
  model_dir: models
backtest:
  train_end: "2026-04-30"
  test_start: "2026-05-01"
  place_cutoff_default: 3
ranker:
  combo_alpha: 8.0
  min_enrich_coverage_pct: 0.0
  min_enrich_coverage_pct: 0.0
""",
        encoding="utf-8",
    )
    monkeypatch.setattr("hibs_racing.config.ROOT", tmp_path)
    init_db(db)
    _seed_runner(db)
    frame = build_ranker_matrix(
        database=db, config_path=cfg_dir / "config.yaml", export_parquet=False, with_enrich=True
    )
    assert len(frame) == 1
    for col in ranker_enrich_feature_columns():
        assert col in frame.columns


def test_impute_enrich_features_adds_all_columns():
    frame = pd.DataFrame(
        {
            "form_string": ["123"],
            "distance_f": [8.0],
            "trainer_14d_wins": [2],
            "trainer_14d_runs": [10],
        }
    )
    out = impute_enrich_features(frame, log_warnings=False)
    for col in ranker_enrich_feature_columns()[36:]:
        assert col in out.columns


def test_stable_hash_is_content_based():
    h1 = compute_stable_hash(features=["a", "b"], ranker_tier="enrich_48", holdout_top1=0.31)
    h2 = compute_stable_hash(features=["b", "a"], ranker_tier="enrich_48", holdout_top1=0.31)
    assert h1 == h2
    assert len(h1) == 16


def test_write_ranker_manifest(tmp_path, monkeypatch):
    monkeypatch.setattr("hibs_racing.config.ROOT", tmp_path)
    cfg_dir = tmp_path / "ingest"
    cfg_dir.mkdir()
    (cfg_dir / "config.yaml").write_text(
        """
paths:
  model_dir: data/models
ranker:
  manifest_file: ranker_manifest.json
""",
        encoding="utf-8",
    )
    manifest = write_ranker_manifest(
        features=["a", "b"],
        ranker_tier="base_36",
        holdout_top1=0.33,
        config_path=cfg_dir / "config.yaml",
    )
    assert manifest["stable_hash"]
    assert json.loads((tmp_path / "data" / "models" / "ranker_manifest.json").read_text())["feature_count"] == 2


def test_backfill_runner_enrich_loose_join_without_off_time(tmp_path, monkeypatch):
    """Historical raceform rows lack off_time — loose date|course|horse join must work."""
    db = tmp_path / "t.sqlite"
    monkeypatch.setenv("HIBS_RACING_DB_PATH", str(db))
    init_db(db)
    with connect(db) as conn:
        conn.execute(
            """
            INSERT INTO runners (
                runner_id, race_id, race_date, horse_id, course, finish_pos, field_size,
                comment_raw, comment_norm, ingested_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'x', 'x', 'now')
            """,
            ("907280:a_dream_to_share_(ire)", "r1", "2026-04-01", "A Dream To Share (IRE)", "Ascot", 1, 8),
        )
        conn.commit()
    cards_dir = tmp_path / "racecards"
    cards_dir.mkdir()
    payload = {
        "gb": {
            "Ascot": {
                "14:30": {
                    "race_id": "r1",
                    "date": "2026-04-01",
                    "course": "Ascot",
                    "off_time": "14:30",
                    "runners": [
                        {
                            "name": "A Dream To Share",
                            "trainer_rtf": "18%",
                            "form": "123",
                            "stats": {},
                        }
                    ],
                }
            }
        }
    }
    (cards_dir / "2026-04-01.json").write_text(json.dumps(payload), encoding="utf-8")
    result = backfill_runner_enrich(database=db, racecards_dir=cards_dir, include_upcoming=False)
    assert result["rows_updated"] >= 1
    assert result["loose_join_matches"] >= 1
    with connect(db) as conn:
        rtf = conn.execute("SELECT trainer_rtf FROM runners WHERE runner_id = ?", ("907280:a_dream_to_share_(ire)",)).fetchone()[0]
    assert float(rtf) == 18.0


def test_backfill_runner_enrich_from_racecards(tmp_path, monkeypatch):
    db = tmp_path / "t.sqlite"
    monkeypatch.setenv("HIBS_RACING_DB_PATH", str(db))
    init_db(db)
    _seed_runner(db)
    cards_dir = tmp_path / "racecards"
    cards_dir.mkdir()
    payload = {
        "gb": {
            "Ascot": {
                "14:30": {
                    "race_id": "r1",
                    "date": "2026-04-01",
                    "course": "Ascot",
                    "off_time": "14:30",
                    "runners": [
                        {
                            "name": "Horse One",
                            "horse_id": "h1",
                            "trainer_rtf": "25%",
                            "form": "123",
                            "stats": {},
                        }
                    ],
                }
            }
        }
    }
    (cards_dir / "2026-04-01.json").write_text(json.dumps(payload), encoding="utf-8")
    result = backfill_runner_enrich(database=db, racecards_dir=cards_dir, include_upcoming=False)
    assert result["rows_updated"] >= 1
    assert result["loose_join_matches"] + result["strict_join_matches"] >= 1
    with connect(db) as conn:
        rtf = conn.execute("SELECT trainer_rtf FROM runners WHERE runner_id = 'r1:h1'").fetchone()[0]
    assert float(rtf) == 25.0
