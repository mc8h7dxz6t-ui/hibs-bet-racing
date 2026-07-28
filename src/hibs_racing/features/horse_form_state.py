"""Autonomous horse form state — μ (EWMA speed delta) and σ (sample uncertainty)."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional

import numpy as np
import pandas as pd

from hibs_racing.config import db_path as racing_db_path
from hibs_racing.features.speed_figure import compute_speed_deltas
from hibs_racing.features.store import connect as store_connect

SIGMA_MIN = 0.05
SIGMA_MAX = 1.0
DEFAULT_SIGMA = 0.45
EWMA_ALPHA = 0.25

HORSE_TRACKER_RANKER_FEATURES: tuple[str, ...] = (
    "speed_delta_lto",
    "ewma_speed_delta",
    "sample_uncertainty_sigma",
)


def _ensure_horse_form_table(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS horse_form_state (
            horse_id TEXT NOT NULL,
            as_of_date TEXT NOT NULL,
            ewma_speed_delta REAL,
            speed_delta_lto REAL,
            sample_uncertainty REAL NOT NULL DEFAULT 0.45,
            runs_90d INTEGER NOT NULL DEFAULT 0,
            last_race_id TEXT,
            meta_json TEXT,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (horse_id, as_of_date)
        );
        CREATE INDEX IF NOT EXISTS idx_horse_form_horse ON horse_form_state (horse_id, as_of_date DESC);
        """
    )


def upsert_horse_state(
    conn: sqlite3.Connection,
    *,
    horse_id: str,
    as_of_date: str,
    ewma_speed_delta: float | None,
    speed_delta_lto: float | None,
    sample_uncertainty: float,
    runs_90d: int,
    last_race_id: str | None,
    meta: Optional[Dict[str, Any]] = None,
) -> None:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    conn.execute(
        """
        INSERT INTO horse_form_state (
            horse_id, as_of_date, ewma_speed_delta, speed_delta_lto,
            sample_uncertainty, runs_90d, last_race_id, meta_json, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(horse_id, as_of_date) DO UPDATE SET
            ewma_speed_delta=excluded.ewma_speed_delta,
            speed_delta_lto=excluded.speed_delta_lto,
            sample_uncertainty=excluded.sample_uncertainty,
            runs_90d=excluded.runs_90d,
            last_race_id=excluded.last_race_id,
            meta_json=excluded.meta_json,
            updated_at=excluded.updated_at
        """,
        (
            horse_id,
            as_of_date,
            ewma_speed_delta,
            speed_delta_lto,
            max(SIGMA_MIN, min(SIGMA_MAX, float(sample_uncertainty))),
            int(runs_90d),
            last_race_id,
            json.dumps(meta or {}, sort_keys=True),
            now,
        ),
    )


def get_horse_state(conn: sqlite3.Connection, horse_id: str, *, as_of: Optional[str] = None) -> Optional[Dict[str, Any]]:
    if as_of:
        row = conn.execute(
            """
            SELECT * FROM horse_form_state
            WHERE horse_id = ? AND as_of_date <= ?
            ORDER BY as_of_date DESC LIMIT 1
            """,
            (horse_id, as_of),
        ).fetchone()
    else:
        row = conn.execute(
            """
            SELECT * FROM horse_form_state
            WHERE horse_id = ?
            ORDER BY as_of_date DESC LIMIT 1
            """,
            (horse_id,),
        ).fetchone()
    return dict(row) if row else None


def sigma_from_runs(n_runs: int) -> float:
    """High σ when sample thin; decays with runs."""
    if n_runs <= 0:
        return DEFAULT_SIGMA
    if n_runs >= 12:
        return SIGMA_MIN + 0.05
    return max(SIGMA_MIN, DEFAULT_SIGMA * (1.0 - n_runs / 16.0))


def impute_horse_tracker_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Fill tracker ranker columns (neutral defaults when missing)."""
    out = frame.copy()
    defaults = {
        "speed_delta_lto": 0.0,
        "ewma_speed_delta": 0.0,
        "sample_uncertainty_sigma": DEFAULT_SIGMA,
    }
    for col, default in defaults.items():
        if col not in out.columns:
            out[col] = default
        else:
            out[col] = pd.to_numeric(out[col], errors="coerce").fillna(default)
    return out


def attach_horse_tracker_features(frame: pd.DataFrame, conn: sqlite3.Connection) -> pd.DataFrame:
    """Point-in-time join horse_form_state onto runner rows (leakage-safe)."""
    out = frame.copy()
    if out.empty or "horse_id" not in out.columns:
        return impute_horse_tracker_features(out)

    try:
        states = pd.read_sql_query(
            """
            SELECT horse_id, as_of_date, ewma_speed_delta, speed_delta_lto, sample_uncertainty
            FROM horse_form_state
            """,
            conn,
        )
    except Exception:
        return impute_horse_tracker_features(out)

    if states.empty:
        return impute_horse_tracker_features(out)

    states = states.copy()
    states["horse_id"] = states["horse_id"].astype(str)
    states["as_of_date"] = states["as_of_date"].astype(str).str[:10]
    states = states.sort_values(["horse_id", "as_of_date"])
    states = states.rename(columns={"sample_uncertainty": "sample_uncertainty_sigma"})

    work = out.copy()
    work["horse_id"] = work["horse_id"].astype(str)
    work["_race_dt"] = pd.to_datetime(work.get("race_date", work.get("card_date")).astype(str).str[:10], errors="coerce")
    states["as_of_dt"] = pd.to_datetime(states["as_of_date"].astype(str).str[:10], errors="coerce")
    work = work.sort_values(["horse_id", "_race_dt"])
    states = states.sort_values(["horse_id", "as_of_dt"])

    merged = pd.merge_asof(
        work,
        states,
        left_on="_race_dt",
        right_on="as_of_dt",
        by="horse_id",
        direction="backward",
    )
    merged = merged.drop(columns=["_race_dt", "as_of_dt", "as_of_date"], errors="ignore")
    return impute_horse_tracker_features(merged)


def sync_horse_form_state_from_runners(
    *,
    since: Optional[str] = None,
    limit: int = 50000,
) -> Dict[str, Any]:
    """Walk historical runners chronologically; update horse_form_state autonomously."""
    with store_connect(racing_db_path()) as conn:
        _ensure_horse_form_table(conn)
        q = "SELECT * FROM runners WHERE finish_pos IS NOT NULL"
        params: List[Any] = []
        if since:
            q += " AND race_date >= ?"
            params.append(since)
        q += " ORDER BY race_date ASC, race_id ASC LIMIT ?"
        params.append(int(limit))
        rows = conn.execute(q, params).fetchall()
        if not rows:
            return {"ok": True, "updated": 0, "reason": "no_rows"}

        frame = pd.DataFrame([dict(r) for r in rows])
        frame = compute_speed_deltas(frame)

        ewma: Dict[str, float] = {}
        runs: Dict[str, int] = {}
        updated = 0
        for _, row in frame.iterrows():
            hid = str(row.get("horse_id") or "").strip()
            if not hid:
                continue
            delta = row.get("speed_figure_delta")
            if delta is None or (isinstance(delta, float) and pd.isna(delta)):
                continue
            try:
                d = float(delta)
            except (TypeError, ValueError):
                continue
            prev = ewma.get(hid, 0.0)
            n = runs.get(hid, 0) + 1
            runs[hid] = n
            new_ewma = prev * (1.0 - EWMA_ALPHA) + d * EWMA_ALPHA if n > 1 else d
            ewma[hid] = new_ewma
            as_of = str(row.get("race_date") or "")[:10]
            upsert_horse_state(
                conn,
                horse_id=hid,
                as_of_date=as_of,
                ewma_speed_delta=new_ewma,
                speed_delta_lto=d,
                sample_uncertainty=sigma_from_runs(n),
                runs_90d=min(n, 90),
                last_race_id=str(row.get("race_id") or ""),
                meta={"stratify_key": row.get("stratify_key")},
            )
            updated += 1
        conn.commit()
    return {"ok": True, "updated": updated, "horses": len(ewma)}
