from __future__ import annotations

import pandas as pd

from hibs_racing.config import db_path, load_config
from hibs_racing.features.store import connect, init_db
from hibs_racing.cards.ui_frame import sanitize_scored_frame
from hibs_racing.place.hpl_combinatorial import apply_place_alpha_and_liquidity


def _inject_offered_place_decimal(frame: pd.DataFrame) -> pd.DataFrame:
    """Derive place back price from win + EW terms when not already on the row."""
    if frame.empty or "win_decimal" not in frame.columns:
        return frame
    out = frame.copy()
    if "offered_place_decimal" not in out.columns:
        out["offered_place_decimal"] = pd.NA
    cfg = load_config().get("paper", {})
    default_frac = float(cfg.get("default_place_fraction", 0.25))
    for idx, row in out.iterrows():
        if pd.notna(row.get("offered_place_decimal")):
            continue
        win = row.get("win_decimal")
        if win is None or (isinstance(win, float) and pd.isna(win)):
            continue
        try:
            win_f = float(win)
        except (TypeError, ValueError):
            continue
        if win_f <= 1.0:
            continue
        frac = row.get("place_fraction")
        try:
            pf = float(frac) if frac is not None and not (isinstance(frac, float) and pd.isna(frac)) else default_frac
        except (TypeError, ValueError):
            pf = default_frac
        out.at[idx, "offered_place_decimal"] = round(1.0 + (win_f - 1.0) * pf, 2)
    return out


def load_scored_cards(*, sanitize: bool = True) -> pd.DataFrame:
    db = db_path(load_config())
    init_db(db)
    with connect(db) as conn:
        frame = pd.read_sql_query(
            """
            SELECT u.*, c.model_score, c.model_win_prob, c.model_place_prob,
                   c.combo_bayes_place, c.hidden_potential, c.nlp_pace_rank,
                   c.jockey_bayes_place, c.trainer_bayes_place,
                   c.jockey_place_90d, c.trainer_place_90d,
                   c.place_ev, c.ew_combined_ev,
                   COALESCE(c.value_flag, 0) AS value_flag,
                   c.value_gate_reason,
                   c.scoring_method, c.scored_at
            FROM upcoming_runners u
            LEFT JOIN card_scores c ON c.runner_id = u.runner_id
            ORDER BY u.card_date, u.off_time, u.course, c.model_place_prob DESC
            """,
            conn,
        )
    if sanitize:
        frame = sanitize_scored_frame(frame)
    frame = _inject_offered_place_decimal(frame)
    return apply_place_alpha_and_liquidity(frame)
