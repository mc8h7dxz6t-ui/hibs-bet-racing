from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from hibs_racing.cards.actionability import apply_value_gates
from hibs_racing.config import db_path, load_config
from hibs_racing.features.store import connect, init_db


@dataclass
class GateCompareReport:
    card_dates: list[str]
    rows: int
    races: int
    raw_value_flags: int
    gated_value_flags: int
    blocked_by_gates: int
    gate_block_rate: float | None
    reason_counts: dict[str, int]
    message: str

    def to_dict(self) -> dict:
        return {
            "card_dates": self.card_dates,
            "rows": self.rows,
            "races": self.races,
            "raw_value_flags": self.raw_value_flags,
            "gated_value_flags": self.gated_value_flags,
            "blocked_by_gates": self.blocked_by_gates,
            "gate_block_rate": round(self.gate_block_rate, 4) if self.gate_block_rate is not None else None,
            "reason_counts": self.reason_counts,
            "message": self.message,
        }


def _load_scored_cards_for_dates(db: Path, dates: list[str]) -> pd.DataFrame:
    if not dates:
        return pd.DataFrame()
    placeholders = ",".join("?" for _ in dates)
    sql = f"""
    SELECT
        u.runner_id,
        u.race_id,
        u.card_date,
        u.race_name,
        u.official_rating,
        u.field_size,
        u.horse_distance_runs,
        u.horse_distance_wins,
        u.form_trip_change_f,
        u.trainer_rtf,
        u.form_poor_runs_3,
        c.place_ev,
        c.combo_bayes_place
    FROM upcoming_runners u
    JOIN card_scores c ON c.runner_id = u.runner_id
    WHERE u.card_date IN ({placeholders})
    """
    with connect(db) as conn:
        return pd.read_sql_query(sql, conn, params=dates)


def compare_value_gates(*, days: int = 14, database: Path | None = None) -> GateCompareReport:
    cfg = load_config()
    db = database or db_path(cfg)
    init_db(db)

    with connect(db) as conn:
        date_rows = conn.execute(
            """
            SELECT DISTINCT card_date
            FROM upcoming_runners
            ORDER BY card_date DESC
            LIMIT ?
            """,
            (max(1, int(days)),),
        ).fetchall()
    card_dates = sorted(str(r[0]) for r in date_rows if r and r[0])
    if not card_dates:
        return GateCompareReport(
            card_dates=[],
            rows=0,
            races=0,
            raw_value_flags=0,
            gated_value_flags=0,
            blocked_by_gates=0,
            gate_block_rate=None,
            reason_counts={},
            message="No stored card dates found in upcoming_runners.",
        )

    frame = _load_scored_cards_for_dates(db, card_dates)
    if frame.empty:
        return GateCompareReport(
            card_dates=card_dates,
            rows=0,
            races=0,
            raw_value_flags=0,
            gated_value_flags=0,
            blocked_by_gates=0,
            gate_block_rate=None,
            reason_counts={},
            message="No scored card rows found for selected dates. Run refresh-cards first.",
        )

    paper_cfg = cfg.get("paper", {})
    min_place_ev = float(paper_cfg.get("min_place_ev", 0.05))
    min_combo_place = float(paper_cfg.get("min_combo_bayes_place", 0.22))

    out = frame.copy()
    out["place_ev"] = pd.to_numeric(out["place_ev"], errors="coerce")
    out["combo_bayes_place"] = pd.to_numeric(out["combo_bayes_place"], errors="coerce")
    out["value_flag"] = (
        (out["place_ev"] >= min_place_ev) & (out["combo_bayes_place"] >= min_combo_place)
    ).astype(int)

    gated = apply_value_gates(out, paper_cfg)
    raw_flags = int(out["value_flag"].sum())
    gated_flags = int(gated["value_flag"].sum())
    blocked = max(0, raw_flags - gated_flags)
    reason_counts = (
        gated["value_gate_reason"]
        .dropna()
        .astype(str)
        .value_counts()
        .sort_values(ascending=False)
        .to_dict()
    )
    block_rate = (blocked / raw_flags) if raw_flags else None

    msg = (
        f"Compared raw vs gated value flags over {len(card_dates)} card day(s): "
        f"{raw_flags} raw, {gated_flags} after gates."
    )
    return GateCompareReport(
        card_dates=card_dates,
        rows=len(gated),
        races=int(gated["race_id"].nunique()) if "race_id" in gated.columns else 0,
        raw_value_flags=raw_flags,
        gated_value_flags=gated_flags,
        blocked_by_gates=blocked,
        gate_block_rate=block_rate,
        reason_counts=reason_counts,
        message=msg,
    )
