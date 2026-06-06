"""Strict NaN / DB–UI integrity monitoring (no email — CLI, health API, logs only)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from hibs_racing.cards.query import load_scored_cards
from hibs_racing.cards.ui_frame import db_ui_sync_report, gate_reason_is_clear, is_value_pick, safe_value_mask
from hibs_racing.config import db_path, load_config
from hibs_racing.features.store import connect, init_db

logger = logging.getLogger(__name__)

# In-memory frame columns that must not contain NaN when is_scored=True.
_SCORED_REQUIRED = (
    "model_score",
    "model_win_prob",
    "model_place_prob",
    "value_flag",
)


@dataclass
class NanAlertReport:
    passed: bool
    violations: list[dict[str, Any]] = field(default_factory=list)
    db_ui_sync: dict[str, Any] = field(default_factory=dict)
    slippage_sample_size: int = 0
    slippage_min_races_for_vps: int = 300
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "violations": self.violations,
            "db_ui_sync": self.db_ui_sync,
            "slippage_sample_size": self.slippage_sample_size,
            "slippage_min_races_for_vps": self.slippage_min_races_for_vps,
            "vps_ready": self.slippage_sample_size >= self.slippage_min_races_for_vps,
            "message": self.message,
        }


def _slippage_race_count(db: Path) -> int:
    init_db(db)
    with connect(db) as conn:
        row = conn.execute(
            """
            SELECT COUNT(DISTINCT card_date || '|' || COALESCE(race_id, ''))
            FROM value_pick_execution
            WHERE closing_sp IS NOT NULL AND baseline_back IS NOT NULL
            """
        ).fetchone()
    return int(row[0] or 0) if row else 0


def run_nan_integrity_check(
    *,
    database: Path | None = None,
    strict: bool = True,
    max_violation_rows: int = 25,
) -> NanAlertReport:
    """
    Fail closed on:
    - unscored upcoming runners (UI would show blank model columns)
    - orphan card_scores
    - NULL value_flag or NaN on scored value picks
    - NaN model fields on rows marked scored
    """
    cfg = load_config()
    db = database or db_path(cfg)
    violations: list[dict[str, Any]] = []

    sync = db_ui_sync_report(database=db)
    if sync["unscored_on_card"] > 0:
        violations.append(
            {
                "code": "unscored_runners_on_card",
                "count": sync["unscored_on_card"],
                "detail": "upcoming_runners without card_scores — run refresh-cards to score",
            }
        )
    if sync["orphan_card_scores"] > 0:
        violations.append(
            {
                "code": "orphan_card_scores",
                "count": sync["orphan_card_scores"],
                "detail": "card_scores rows not in upcoming_runners — run data-integrity-check --repair",
            }
        )
    if sync["nan_value_flags"] > 0:
        violations.append(
            {
                "code": "nan_value_flag_in_db",
                "count": sync["nan_value_flags"],
                "detail": "NULL value_flag in card_scores",
            }
        )
    if sync["nan_value_pick_ev"] > 0:
        violations.append(
            {
                "code": "nan_value_pick_ev",
                "count": sync["nan_value_pick_ev"],
                "detail": "value_flag=1 but ew_combined_ev is NULL/NaN",
            }
        )
    if sync["nan_model_place_prob"] > 0:
        violations.append(
            {
                "code": "nan_model_place_prob_in_db",
                "count": sync["nan_model_place_prob"],
                "detail": "scored rows with NULL model_place_prob",
            }
        )

    frame = load_scored_cards()
    if not frame.empty:
        if "is_scored" in frame.columns:
            scored_rows = frame[frame["is_scored"] == True]  # noqa: E712
        elif "scored_at" in frame.columns:
            scored_rows = frame[frame["scored_at"].notna()]
        else:
            scored_rows = frame[frame["model_score"].notna()]

        for col in _SCORED_REQUIRED:
            if col not in scored_rows.columns:
                continue
            bad = scored_rows[scored_rows[col].apply(_frame_val_nan)]
            if not bad.empty:
                violations.append(
                    {
                        "code": f"frame_nan_{col}",
                        "count": len(bad),
                        "detail": f"NaN in {col} on scored UI rows",
                        "sample_runner_ids": bad["runner_id"].astype(str).head(5).tolist(),
                    }
                )

        value_picks = frame[safe_value_mask(frame)]
        if not value_picks.empty and "value_gate_reason" in value_picks.columns:
            blocked_with_flag = sum(
                1
                for rec in value_picks.to_dict(orient="records")
                if not gate_reason_is_clear(rec.get("value_gate_reason"))
            )
            if blocked_with_flag:
                violations.append(
                    {
                        "code": "value_flag_with_block_reason",
                        "count": blocked_with_flag,
                        "detail": "value_flag=1 but value_gate_reason is set — gate logic bug",
                    }
                )
        if not value_picks.empty and "ew_combined_ev" in value_picks.columns:
            bad_ev = value_picks[value_picks["ew_combined_ev"].apply(_frame_val_nan)]
            if not bad_ev.empty:
                violations.append(
                    {
                        "code": "frame_nan_value_pick_ev",
                        "count": len(bad_ev),
                        "detail": "VALUE picks with NaN ew_combined_ev in UI frame",
                        "sample_runner_ids": bad_ev["runner_id"].astype(str).head(5).tolist(),
                    }
                )

    slippage_n = _slippage_race_count(db)
    min_vps = int(cfg.get("exchange_profiling", {}).get("min_races_before_vps", 300))

    passed = len(violations) == 0
    if strict and not passed:
        for v in violations[:max_violation_rows]:
            logger.error("NAN_INTEGRITY %s: %s", v.get("code"), v.get("detail"))
        logger.error(
            "NAN_INTEGRITY FAILED — %s violation(s). DB sync: %s%% scored on card.",
            len(violations),
            sync.get("sync_pct"),
        )

    msg = "NaN integrity OK." if passed else f"NaN integrity FAILED ({len(violations)} issue(s))."
    return NanAlertReport(
        passed=passed,
        violations=violations[:max_violation_rows],
        db_ui_sync=sync,
        slippage_sample_size=slippage_n,
        slippage_min_races_for_vps=min_vps,
        message=msg,
    )


def _frame_val_nan(val: object) -> bool:
    if val is None:
        return True
    if isinstance(val, float):
        return bool(pd.isna(val))
    try:
        return bool(pd.isna(val))
    except (TypeError, ValueError):
        return False
