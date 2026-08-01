"""Materialized engine_runner_features — fast engine reads without full ranker recompute."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from hibs_racing.cards.data_quality import runner_data_quality_pct
from hibs_racing.config import db_path, load_config
from hibs_racing.features.ranker_matrix import ranker_tracker_feature_columns
from hibs_racing.features.store import connect

_SCHEMA_VERSION = 1

ENGINE_RUNNER_DDL = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS engine_runner_features (
    runner_id TEXT PRIMARY KEY,
    race_id TEXT NOT NULL,
    race_natural_key TEXT,
    card_date TEXT,
    course TEXT,
    off_time TEXT,
    horse_name TEXT,
    dq_score_pct REAL,
    model_score REAL,
    model_win_prob REAL,
    model_place_prob REAL,
    combo_bayes_place REAL,
    win_decimal REAL,
    value_flag INTEGER NOT NULL DEFAULT 0,
    features_json TEXT NOT NULL,
    built_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_engine_runner_race ON engine_runner_features (race_id);
CREATE INDEX IF NOT EXISTS idx_engine_runner_natural ON engine_runner_features (race_natural_key);
CREATE INDEX IF NOT EXISTS idx_engine_runner_card ON engine_runner_features (card_date, course, off_time);
"""


def ensure_engine_runner_schema(db: Path) -> None:
    with connect(db) as conn:
        conn.executescript(ENGINE_RUNNER_DDL)
        conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES ('engine_runner_schema_version', ?)",
            (str(_SCHEMA_VERSION),),
        )
        conn.commit()


def _row_dict(rec: pd.Series | Dict[str, Any]) -> Dict[str, Any]:
    if isinstance(rec, pd.Series):
        return {k: (None if pd.isna(v) else v) for k, v in rec.items()}
    return dict(rec)


def build_engine_runner_payload(rec: pd.Series | Dict[str, Any]) -> Dict[str, Any]:
    row = _row_dict(rec)
    ranker_cols = ranker_tracker_feature_columns()
    ranker_inputs = {c: row.get(c) for c in ranker_cols if c in row}
    return {
        "runner_id": row.get("runner_id"),
        "race_id": row.get("race_id"),
        "race_natural_key": row.get("race_natural_key"),
        "card_date": row.get("card_date"),
        "course": row.get("course"),
        "off_time": row.get("off_time"),
        "horse_name": row.get("horse_name"),
        "dq_score_pct": runner_data_quality_pct(row),
        "model_score": row.get("model_score"),
        "model_win_prob": row.get("model_win_prob"),
        "model_place_prob": row.get("model_place_prob"),
        "combo_bayes_place": row.get("combo_bayes_place"),
        "win_decimal": row.get("win_decimal"),
        "value_flag": int(row.get("value_flag") or 0),
        "scoring_method": row.get("scoring_method"),
        "ranker_inputs": ranker_inputs,
    }


def upsert_engine_runner_feature(rec: pd.Series | Dict[str, Any], *, database: Path | None = None) -> bool:
    row = _row_dict(rec)
    runner_id = str(row.get("runner_id") or "").strip()
    if not runner_id:
        return False
    db = database or db_path(load_config())
    ensure_engine_runner_schema(db)
    payload = build_engine_runner_payload(row)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    with connect(db) as conn:
        conn.execute(
            """
            INSERT INTO engine_runner_features (
                runner_id, race_id, race_natural_key, card_date, course, off_time, horse_name,
                dq_score_pct, model_score, model_win_prob, model_place_prob, combo_bayes_place,
                win_decimal, value_flag, features_json, built_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(runner_id) DO UPDATE SET
                race_id=excluded.race_id,
                race_natural_key=excluded.race_natural_key,
                card_date=excluded.card_date,
                course=excluded.course,
                off_time=excluded.off_time,
                horse_name=excluded.horse_name,
                dq_score_pct=excluded.dq_score_pct,
                model_score=excluded.model_score,
                model_win_prob=excluded.model_win_prob,
                model_place_prob=excluded.model_place_prob,
                combo_bayes_place=excluded.combo_bayes_place,
                win_decimal=excluded.win_decimal,
                value_flag=excluded.value_flag,
                features_json=excluded.features_json,
                built_at=excluded.built_at
            """,
            (
                runner_id,
                row.get("race_id"),
                row.get("race_natural_key"),
                row.get("card_date"),
                row.get("course"),
                row.get("off_time"),
                row.get("horse_name"),
                payload.get("dq_score_pct"),
                payload.get("model_score"),
                payload.get("model_win_prob"),
                payload.get("model_place_prob"),
                payload.get("combo_bayes_place"),
                payload.get("win_decimal"),
                int(payload.get("value_flag") or 0),
                json.dumps(payload, sort_keys=True, default=str),
                now,
            ),
        )
        conn.commit()
    return True


def materialize_engine_runner_features(
    frame: pd.DataFrame,
    *,
    database: Path | None = None,
) -> Dict[str, int]:
    written = 0
    skipped = 0
    if frame is None or frame.empty:
        return {"written": 0, "skipped": 0}
    for rec in frame.to_dict(orient="records"):
        if upsert_engine_runner_feature(rec, database=database):
            written += 1
        else:
            skipped += 1
    return {"written": written, "skipped": skipped}


def load_engine_runner_feature(runner_id: str, *, database: Path | None = None) -> Optional[Dict[str, Any]]:
    db = database or db_path(load_config())
    ensure_engine_runner_schema(db)
    with connect(db) as conn:
        row = conn.execute(
            "SELECT features_json FROM engine_runner_features WHERE runner_id = ?",
            (str(runner_id),),
        ).fetchone()
    if not row:
        return None
    try:
        return json.loads(row[0])
    except json.JSONDecodeError:
        return None


def engine_runner_store_status(*, database: Path | None = None) -> Dict[str, Any]:
    db = database or db_path(load_config())
    if not db.is_file():
        return {
            "ok": False,
            "db_exists": False,
            "runner_rows": 0,
            "mean_dq_pct": 0.0,
            "message": "store_not_initialized",
        }
    ensure_engine_runner_schema(db)
    with connect(db) as conn:
        tables = {
            r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        if "engine_runner_features" not in tables:
            return {
                "ok": False,
                "db_exists": True,
                "runner_rows": 0,
                "mean_dq_pct": 0.0,
                "message": "engine_table_missing",
            }
        row = conn.execute(
            """
            SELECT COUNT(*) AS n,
                   AVG(dq_score_pct) AS mean_dq,
                   MAX(built_at) AS latest_built_at
            FROM engine_runner_features
            """
        ).fetchone()
    count = int(row[0] or 0) if row else 0
    mean_dq = round(float(row[1] or 0), 1) if row and row[1] is not None else 0.0
    return {
        "ok": count > 0,
        "db_exists": True,
        "runner_rows": count,
        "mean_dq_pct": mean_dq,
        "latest_built_at": row[2] if row else None,
        "message": "ok" if count > 0 else "empty",
    }


def sync_racing_engine_store_from_scored_cards(*, database: Path | None = None) -> Dict[str, Any]:
    """Materialize engine_runner_features from current scored card frame."""
    from hibs_racing.cards.dq_persist import mean_runner_dq
    from hibs_racing.cards.query import load_scored_cards

    frame = load_scored_cards()
    if frame.empty:
        return {
            "ok": False,
            "reason": "empty_scored_cards",
            "runner_count": 0,
            "engine_written": 0,
            "mean_dq_pct": 0.0,
        }
    mean_before = mean_runner_dq(frame)
    mat = materialize_engine_runner_features(frame, database=database)
    mean_after = mean_runner_dq(frame)
    return {
        "ok": True,
        "runner_count": len(frame),
        "engine_written": int(mat.get("written") or 0),
        "engine_skipped": int(mat.get("skipped") or 0),
        "mean_dq_pct_before": mean_before,
        "mean_dq_pct": mean_after,
        "engine_store": engine_runner_store_status(database=database),
    }
