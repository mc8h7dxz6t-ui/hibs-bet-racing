from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from hibs_racing.config import db_path, load_config
from hibs_racing.features.ranker_matrix import build_card_feature_frame
from hibs_racing.features.store import connect, init_db
from hibs_racing.place.ew_ev import EachWayQuote, each_way_ev
from hibs_racing.place.harville import harville_place_probs
from hibs_racing.place.paper_ledger import record_paper_bet
from hibs_racing.racing_engine.score_card import apply_scoring


def score_upcoming_cards(
    cards: pd.DataFrame,
    *,
    database: Path | None = None,
    odds: pd.DataFrame | None = None,
    persist: bool = True,
    hist_frame: pd.DataFrame | None = None,
    hist_before_date: str | None = None,
) -> pd.DataFrame:
    """Score card runners → win/place probs → optional EW value vs offered odds."""
    cfg = load_config()
    db = database or db_path(cfg)
    paper_cfg = cfg.get("paper", {})
    min_place_ev = paper_cfg.get("min_place_ev", 0.05)
    min_combo_place = paper_cfg.get("min_combo_bayes_place", 0.22)

    frame = build_card_feature_frame(
        cards,
        database=db,
        hist_frame=hist_frame,
        hist_before_date=hist_before_date,
    )
    card_cols = [c for c in cards.columns if c not in frame.columns]
    if card_cols:
        frame = frame.merge(cards[["runner_id"] + card_cols], on="runner_id", how="left")

    frame = apply_scoring(frame)

    place_probs: list[float] = []
    for _, group in frame.groupby("race_id", sort=False):
        wp = group["model_win_prob"].tolist()
        places = min(3, len(wp))
        hp = harville_place_probs(wp, places=places)
        place_probs.extend(hp)

    frame["model_place_prob"] = place_probs
    frame["place_ev"] = np.nan
    frame["ew_combined_ev"] = np.nan
    frame["value_flag"] = 0

    if odds is not None and not odds.empty:
        frame = _merge_odds(frame, odds)
        for idx, row in frame.iterrows():
            if pd.isna(row.get("win_decimal")):
                continue
            quote = EachWayQuote(
                win_decimal=float(row["win_decimal"]),
                place_fraction=float(row.get("place_fraction") or paper_cfg.get("default_place_fraction", 0.25)),
                places=int(row.get("places") or paper_cfg.get("default_places", 3)),
            )
            ev = each_way_ev(float(row["model_win_prob"]), float(row["model_place_prob"]), quote)
            frame.at[idx, "place_ev"] = ev.place_ev
            frame.at[idx, "ew_combined_ev"] = ev.combined_ev
            if (
                ev.place_ev >= min_place_ev
                and float(row["combo_bayes_place"]) >= min_combo_place
            ):
                frame.at[idx, "value_flag"] = 1

    scored_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    if persist:
        _persist_scores(db, frame, scored_at)
        _persist_runner_odds(db, frame)
    return frame.sort_values(["race_id", "model_score"], ascending=[True, False])


def _merge_odds(frame: pd.DataFrame, odds: pd.DataFrame) -> pd.DataFrame:
    odds = odds.copy()
    merged = None
    if "runner_id" in odds.columns and "runner_id" in frame.columns:
        merged = frame.merge(odds, on="runner_id", how="left", suffixes=("", "_odds"))
    if merged is None or (
        "win_decimal_odds" in merged.columns and merged["win_decimal_odds"].notna().sum() == 0
    ):
        if "horse_name" not in odds.columns:
            raise ValueError("odds needs runner_id or horse_name")
        merged = frame.merge(odds, on="horse_name", how="left", suffixes=("", "_odds"))
    for base in ("win_decimal", "place_fraction", "places", "best_book"):
        odds_col = f"{base}_odds"
        if odds_col in merged.columns:
            if base in merged.columns:
                merged[base] = merged[odds_col].combine_first(merged[base])
            else:
                merged[base] = merged[odds_col]
    drop_cols = [c for c in merged.columns if c.endswith("_odds")]
    return merged.drop(columns=drop_cols, errors="ignore")


def _persist_runner_odds(db: Path, frame: pd.DataFrame) -> None:
    """Write merged win/place odds back to upcoming_runners so UI reload keeps full field prices."""
    init_db(db)
    paper_cfg = load_config().get("paper", {})
    default_frac = float(paper_cfg.get("default_place_fraction", 0.25))
    with connect(db) as conn:
        for rec in frame.to_dict(orient="records"):
            win = rec.get("win_decimal")
            frac = rec.get("place_fraction")
            places = rec.get("places")
            offered_place = None
            if win is not None and not (isinstance(win, float) and pd.isna(win)):
                try:
                    win_f = float(win)
                    pf = float(frac) if frac is not None and not (isinstance(frac, float) and pd.isna(frac)) else default_frac
                    if win_f > 1:
                        offered_place = round(1.0 + (win_f - 1.0) * pf, 2)
                except (TypeError, ValueError):
                    pass
            conn.execute(
                """
                UPDATE upcoming_runners
                SET win_decimal = COALESCE(?, win_decimal),
                    place_fraction = COALESCE(?, place_fraction),
                    places = COALESCE(?, places),
                    offered_place_decimal = COALESCE(?, offered_place_decimal)
                WHERE runner_id = ?
                """,
                (
                    float(win) if win is not None and not (isinstance(win, float) and pd.isna(win)) else None,
                    float(frac) if frac is not None and not (isinstance(frac, float) and pd.isna(frac)) else None,
                    int(places) if places is not None and not (isinstance(places, float) and pd.isna(places)) else None,
                    offered_place,
                    rec["runner_id"],
                ),
            )
        conn.commit()


def _persist_scores(db: Path, frame: pd.DataFrame, scored_at: str) -> None:
    init_db(db)
    with connect(db) as conn:
        conn.execute("DELETE FROM card_scores")
        for rec in frame.to_dict(orient="records"):
            conn.execute(
                """
                INSERT INTO card_scores (
                    runner_id, race_id, model_score, model_win_prob, model_place_prob,
                    combo_bayes_place, hidden_potential, nlp_pace_rank,
                    jockey_bayes_place, trainer_bayes_place, jockey_place_90d, trainer_place_90d,
                    place_ev, ew_combined_ev, value_flag, scoring_method, scored_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rec["runner_id"],
                    rec["race_id"],
                    float(rec["model_score"]),
                    rec.get("model_win_prob"),
                    rec.get("model_place_prob"),
                    rec.get("combo_bayes_place"),
                    rec.get("hidden_potential"),
                    rec.get("nlp_pace_rank"),
                    rec.get("jockey_bayes_place"),
                    rec.get("trainer_bayes_place"),
                    rec.get("jockey_place_90d"),
                    rec.get("trainer_place_90d"),
                    rec.get("place_ev") if pd.notna(rec.get("place_ev")) else None,
                    rec.get("ew_combined_ev") if pd.notna(rec.get("ew_combined_ev")) else None,
                    int(rec.get("value_flag") or 0),
                    rec.get("scoring_method"),
                    scored_at,
                ),
            )
        conn.commit()


def paper_log_value_picks(
    frame: pd.DataFrame,
    *,
    stake: float = 1.0,
    backtest: bool = False,
    created_at: str | None = None,
) -> list[str]:
    """Record paper EW bets for rows flagged as value."""
    bet_ids: list[str] = []
    for rec in frame[frame["value_flag"] == 1].to_dict(orient="records"):
        bet_id = record_paper_bet(
            rec["race_id"],
            rec["runner_id"],
            "each_way",
            stake,
            model_ev=rec.get("ew_combined_ev"),
            offered_win=rec.get("win_decimal"),
            place_terms=f"1/{int((rec.get('place_fraction') or 0.25)*4)} top {int(rec.get('places') or 3)}",
            is_value_pick=True,
            backtest=backtest,
            created_at=created_at,
        )
        bet_ids.append(bet_id)
    return bet_ids


def top_place_picks(frame: pd.DataFrame, *, per_race: int = 2) -> pd.DataFrame:
    """Human-readable shortlist sorted by model place prob."""
    cols = [
        "card_date",
        "off_time",
        "course",
        "race_name",
        "horse_name",
        "jockey",
        "trainer",
        "combo_bayes_place",
        "model_place_prob",
        "hidden_potential",
        "nlp_pace_rank",
        "value_flag",
        "ew_combined_ev",
        "scoring_method",
    ]
    use = [c for c in cols if c in frame.columns]
    return (
        frame.sort_values(["race_id", "model_place_prob"], ascending=[True, False])
        .groupby("race_id", sort=False)
        .head(per_race)[use]
    )
