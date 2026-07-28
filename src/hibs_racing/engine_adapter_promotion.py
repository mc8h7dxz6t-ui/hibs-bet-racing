"""Promotion gates for racing ranker v2 (horse tracker features)."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from hibs_racing.config import db_path, load_config
from hibs_racing.features.store import connect

_GATE_SCHEMA = "racing_ranker_v2_v1"
_DEFAULT_MIN_DAYS = 28


def _ensure_shadow_table(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS ranker_v2_shadow_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            race_id TEXT NOT NULL,
            runner_id TEXT NOT NULL,
            race_date TEXT NOT NULL,
            logged_at TEXT NOT NULL,
            production_score REAL,
            shadow_score REAL,
            place_roi_paper REAL,
            settled INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_ranker_v2_shadow_date ON ranker_v2_shadow_log (race_date);
        """
    )


def record_ranker_v2_shadow_row(
    *,
    race_id: str,
    runner_id: str,
    race_date: str,
    production_score: float,
    shadow_score: float,
) -> None:
    cfg = load_config()
    with connect(db_path(cfg)) as conn:
        _ensure_shadow_table(conn)
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        conn.execute(
            """
            INSERT INTO ranker_v2_shadow_log (
                race_id, runner_id, race_date, logged_at, production_score, shadow_score
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (race_id, runner_id, race_date[:10], now, float(production_score), float(shadow_score)),
        )


def maybe_log_ranker_v2_shadow(frame: pd.DataFrame) -> None:
    """Shadow lane: log production vs tracker-feature coverage for promotion gate."""
    import os

    mode = (os.getenv("HIBS_USE_TRACKER_RANKER") or "shadow").strip().lower()
    if mode in ("0", "off", "false", "no"):
        return
    if frame is None or frame.empty:
        return
    try:
        from hibs_racing.features.horse_form_state import HORSE_TRACKER_RANKER_FEATURES
    except Exception:
        return

    prod = pd.to_numeric(frame.get("model_raw_score", frame.get("model_score")), errors="coerce").fillna(0.0)
    for idx, row in frame.iterrows():
        try:
            tracker_signal = float(row.get("ewma_speed_delta") or 0.0)
            record_ranker_v2_shadow_row(
                race_id=str(row.get("race_id") or ""),
                runner_id=str(row.get("runner_id") or ""),
                race_date=str(row.get("race_date") or row.get("card_date") or "")[:10],
                production_score=float(prod.loc[idx]),
                shadow_score=float(prod.loc[idx] + tracker_signal * 0.01),
            )
        except Exception:
            continue


def evaluate_racing_ranker_v2_gate(
    *,
    min_shadow_days: Optional[int] = None,
    min_samples: int = 200,
) -> Dict[str, Any]:
    min_days = int(min_shadow_days or os.getenv("HIBS_RACING_RANKER_V2_MIN_DAYS", str(_DEFAULT_MIN_DAYS)))
    cfg = load_config()
    db = db_path(cfg)

    horses = 0
    runners = 0
    with connect(db) as conn:
        _ensure_shadow_table(conn)
        try:
            horses = conn.execute("SELECT COUNT(DISTINCT horse_id) FROM horse_form_state").fetchone()[0]
        except sqlite3.OperationalError:
            horses = 0
        runners = conn.execute("SELECT COUNT(*) FROM runners WHERE finish_pos IS NOT NULL").fetchone()[0]
        rows = conn.execute(
            "SELECT race_date, place_roi_paper FROM ranker_v2_shadow_log WHERE settled=1 AND place_roi_paper IS NOT NULL ORDER BY race_date"
        ).fetchall()

    if not rows:
        feature_ready = int(horses or 0) >= 50 and int(runners or 0) >= 500
        return {
            "schema": _GATE_SCHEMA,
            "ok": feature_ready,
            "promote": False,
            "reason": "no_settled_shadow_rows" if feature_ready else "horse_form_state_thin",
            "min_shadow_days": min_days,
            "horse_form_horses": int(horses or 0),
            "runner_rows": int(runners or 0),
            "n_settled": 0,
            "live_env": "HIBS_USE_TRACKER_RANKER=1",
        }

    first = str(rows[0][0])[:10]
    last = str(rows[-1][0])[:10]
    try:
        span_days = (datetime.fromisoformat(last) - datetime.fromisoformat(first)).days + 1
    except ValueError:
        span_days = 0

    rois = [float(r[1]) for r in rows if r[1] is not None]
    mean_roi = sum(rois) / len(rois) if rois else 0.0
    promote = span_days >= min_days and len(rois) >= min_samples and mean_roi > 0.0

    return {
        "schema": _GATE_SCHEMA,
        "ok": True,
        "promote": promote,
        "reason": "ok" if promote else (
            "insufficient_span" if span_days < min_days else
            "insufficient_samples" if len(rois) < min_samples else
            "place_roi_paper_not_positive"
        ),
        "min_shadow_days": min_days,
        "shadow_span_days": span_days,
        "first_race_date": first,
        "last_race_date": last,
        "n_settled": len(rois),
        "mean_place_roi_paper": round(mean_roi, 5),
        "horse_form_horses": int(horses or 0),
        "live_env": "HIBS_USE_TRACKER_RANKER=1",
    }
