from __future__ import annotations

import pandas as pd

from hibs_racing.config import db_path, load_config
from hibs_racing.features.store import connect, init_db


def load_scored_cards() -> pd.DataFrame:
    db = db_path(load_config())
    init_db(db)
    with connect(db) as conn:
        return pd.read_sql_query(
            """
            SELECT u.*, c.model_score, c.model_win_prob, c.model_place_prob,
                   c.combo_bayes_place, c.hidden_potential, c.nlp_pace_rank,
                   c.jockey_bayes_place, c.trainer_bayes_place,
                   c.jockey_place_90d, c.trainer_place_90d,
                   c.place_ev, c.ew_combined_ev, c.value_flag, c.scoring_method, c.scored_at
            FROM upcoming_runners u
            LEFT JOIN card_scores c ON c.runner_id = u.runner_id
            ORDER BY u.card_date, u.off_time, u.course, c.model_place_prob DESC
            """,
            conn,
        )
