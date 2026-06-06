"""Sanitise scored card frames for UI/API — single source of truth from SQLite."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from hibs_racing.config import db_path, load_config
from hibs_racing.features.store import connect, init_db

# Columns that must never surface as NaN/NA in UI or B2B JSON feeds.
_NUMERIC_UI_COLS = (
    "model_score",
    "model_win_prob",
    "model_place_prob",
    "combo_bayes_place",
    "hidden_potential",
    "nlp_pace_rank",
    "jockey_bayes_place",
    "trainer_bayes_place",
    "jockey_place_90d",
    "trainer_place_90d",
    "place_ev",
    "ew_combined_ev",
    "win_decimal",
    "offered_place_decimal",
    "official_rating",
    "draw",
    "distance_f",
)

_FLAG_COLS = ("value_flag", "flag_raw")


def _is_missing(val: Any) -> bool:
    if val is None:
        return True
    if isinstance(val, float) and pd.isna(val):
        return True
    try:
        return bool(pd.isna(val))
    except (TypeError, ValueError):
        return False


def gate_reason_is_clear(reason: Any) -> bool:
    """
    True when the runner is not blocked by an actionability gate.
    Treats None, pandas NA, float NaN, and blank strings as clear (production VALUE rows).
    """
    if _is_missing(reason):
        return True
    if isinstance(reason, str):
        return not reason.strip()
    return False


def is_value_pick(value: Any) -> bool:
    """Robust value_flag check for dict rows and API payloads."""
    if value is True:
        return True
    if value is False:
        return False
    if _is_missing(value):
        return False
    try:
        return int(value) == 1
    except (TypeError, ValueError):
        return False


def normalize_gate_reason_for_db(reason: Any) -> str | None:
    """SQLite TEXT: NULL for passing VALUE rows, stable string codes for blocked rows."""
    if gate_reason_is_clear(reason):
        return None
    return str(reason).strip()


def repair_value_gate_reasons(*, database: Path | None = None) -> int:
    """NULL gate_reason on all VALUE picks (fixes pandas NaN read + legacy Smart Portfolio filter)."""
    db = database or db_path(load_config())
    init_db(db)
    with connect(db) as conn:
        cur = conn.execute(
            "UPDATE card_scores SET value_gate_reason = NULL WHERE value_flag = 1"
        )
        conn.commit()
        return int(cur.rowcount)


def safe_value_mask(frame: pd.DataFrame) -> pd.Series:
    """True where value_flag is definitively 1 (never NA-sensitive)."""
    if frame.empty or "value_flag" not in frame.columns:
        return pd.Series(dtype=bool)
    return pd.to_numeric(frame["value_flag"], errors="coerce").fillna(0).astype(int).eq(1)


def sanitize_scored_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Coerce DB NULLs to UI-safe values; keep unscored runners but mark them."""
    if frame.empty:
        return frame
    out = frame.copy()
    if "scored_at" in out.columns:
        out["is_scored"] = out["scored_at"].notna()
    else:
        out["is_scored"] = out["model_score"].notna() if "model_score" in out.columns else False

    for col in _FLAG_COLS:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0).astype(int)

    for col in _NUMERIC_UI_COLS:
        if col not in out.columns:
            continue
        out[col] = pd.to_numeric(out[col], errors="coerce")

    if "value_gate_reason" in out.columns:
        out["value_gate_reason"] = out["value_gate_reason"].where(out["value_gate_reason"].notna(), None)

    return out


def db_ui_sync_report(*, database: Path | None = None) -> dict[str, Any]:
    """
    Measure card_scores ↔ upcoming_runners alignment.
    UI reads the LEFT JOIN in load_scored_cards; this exposes drift.
    """
    db = database or db_path(load_config())
    init_db(db)
    with connect(db) as conn:
        upcoming = int(conn.execute("SELECT COUNT(*) FROM upcoming_runners").fetchone()[0])
        scored = int(conn.execute("SELECT COUNT(*) FROM card_scores").fetchone()[0])
        unscored = int(
            conn.execute(
                """
                SELECT COUNT(*) FROM upcoming_runners u
                LEFT JOIN card_scores c ON c.runner_id = u.runner_id
                WHERE c.runner_id IS NULL
                """
            ).fetchone()[0]
        )
        orphan_scores = int(
            conn.execute(
                """
                SELECT COUNT(*) FROM card_scores c
                WHERE NOT EXISTS (
                    SELECT 1 FROM upcoming_runners u WHERE u.runner_id = c.runner_id
                )
                """
            ).fetchone()[0]
        )
        nan_flags = int(
            conn.execute(
                """
                SELECT COUNT(*) FROM card_scores
                WHERE value_flag IS NULL
                """
            ).fetchone()[0]
        )
        nan_ev = int(
            conn.execute(
                """
                SELECT COUNT(*) FROM card_scores
                WHERE value_flag = 1
                  AND (ew_combined_ev IS NULL OR ew_combined_ev != ew_combined_ev)
                """
            ).fetchone()[0]
        )
        nan_model = int(
            conn.execute(
                """
                SELECT COUNT(*) FROM card_scores
                WHERE model_place_prob IS NULL OR model_place_prob != model_place_prob
                """
            ).fetchone()[0]
        )

    scored_on_card = upcoming - unscored
    sync_pct = round(100.0 * scored_on_card / upcoming, 2) if upcoming else 100.0
    in_sync = unscored == 0 and orphan_scores == 0 and nan_flags == 0 and nan_model == 0

    return {
        "upcoming_runners": upcoming,
        "card_scores_rows": scored,
        "scored_on_card": scored_on_card,
        "unscored_on_card": unscored,
        "orphan_card_scores": orphan_scores,
        "nan_value_flags": nan_flags,
        "nan_value_pick_ev": nan_ev,
        "nan_model_place_prob": nan_model,
        "sync_pct": sync_pct,
        "in_sync": in_sync,
    }


def prune_orphan_card_scores(*, database: Path | None = None) -> int:
    """Remove card_scores rows with no matching upcoming_runner (post-refresh cleanup)."""
    db = database or db_path(load_config())
    init_db(db)
    with connect(db) as conn:
        cur = conn.execute(
            """
            DELETE FROM card_scores
            WHERE NOT EXISTS (
                SELECT 1 FROM upcoming_runners u WHERE u.runner_id = card_scores.runner_id
            )
            """
        )
        conn.commit()
        return int(cur.rowcount)
