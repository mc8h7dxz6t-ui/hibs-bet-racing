from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from hibs_racing.cards.harville_config import harville_longshot_discount
from hibs_racing.config import db_path, load_config
from hibs_racing.features.ranker_matrix import build_card_feature_frame
from hibs_racing.features.store import connect
from hibs_racing.models.win_engine_config import win_engine_active
from hibs_racing.models.win_engine_store import ensure_win_engine_schema, upsert_predictions
from hibs_racing.place.harville import harville_place_probs
from hibs_racing.racing_engine.score_card import apply_scoring


def _env_float(name: str, default: float) -> float:
    import os

    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def compute_market_velocity(live_odds: pd.Series, race_ids: pd.Series) -> pd.Series:
    """Runner implied share relative to field sum."""
    implied = 1.0 / pd.to_numeric(live_odds, errors="coerce").clip(lower=1.01)
    return implied.groupby(race_ids, sort=False).transform(lambda s: s / s.sum() if s.sum() > 0 else 1.0 / len(s))


def mcfadden_conditional_logit(
    race_df: pd.DataFrame,
    *,
    x_col: str = "x_fund",
    odds_col: str = "live_odds_decimal",
    alpha: float | None = None,
    beta: float | None = None,
) -> pd.DataFrame:
    """
    McFadden conditional logit with market utility per race cluster.
    V_i = alpha * X_fund_i + beta * log(market_velocity_i)
    P_i = softmax(V_i) ensuring sum(P) == 1.0 per race_id.
    """
    alpha = alpha if alpha is not None else _env_float("HIBS_WIN_ENGINE_ALPHA", 1.0)
    beta = beta if beta is not None else _env_float("HIBS_WIN_ENGINE_BETA", 0.35)

    out = race_df.copy()
    x = pd.to_numeric(out[x_col], errors="coerce").fillna(0.0)
    odds = pd.to_numeric(out[odds_col], errors="coerce").fillna(np.nan)
    implied = 1.0 / odds.clip(lower=1.01)
    market_velocity = implied.groupby(out["race_id"], sort=False).transform(
        lambda s: s / s.sum() if s.sum() > 0 else 1.0 / len(s)
    )
    market_velocity = market_velocity.fillna(1.0 / out.groupby("race_id", sort=False)[odds_col].transform("count"))
    out["market_velocity"] = market_velocity

    utility = alpha * x + beta * np.log(market_velocity.clip(lower=1e-9))
    max_u = utility.groupby(out["race_id"], sort=False).transform("max")
    exp_u = np.exp(utility - max_u)
    sum_exp = exp_u.groupby(out["race_id"], sort=False).transform("sum")
    field_n = out.groupby("race_id", sort=False)[x_col].transform("count")
    true_prob = np.where(sum_exp > 0, exp_u / sum_exp, 1.0 / field_n)
    out["true_probability"] = true_prob
    out["fair_odds"] = np.where(true_prob > 0, 1.0 / true_prob, np.nan)
    return out


def _attach_place_probs(frame: pd.DataFrame) -> pd.DataFrame:
    cfg = load_config()
    paper_cfg = cfg.get("paper", {})
    longshot_threshold = float(paper_cfg.get("harville_longshot_win_prob_threshold", 0.03))
    longshot_discount = harville_longshot_discount(float(paper_cfg.get("harville_longshot_discount", 1.0)))
    place_probs: list[float] = []
    for _, group in frame.groupby("race_id", sort=False):
        wp = group["true_probability"].tolist()
        places = min(3, len(wp))
        hp = harville_place_probs(
            wp,
            places=places,
            longshot_win_prob_threshold=longshot_threshold,
            longshot_discount=longshot_discount,
        )
        place_probs.extend(hp)
    out = frame.copy()
    out["place_probability"] = place_probs
    return out


def _resolve_matchbook_back_odds(row: pd.Series) -> float | None:
    """Exchange back price used for de-vig market Brier overlay."""
    if "matchbook_back_odds" in row.index and pd.notna(row.get("matchbook_back_odds")):
        val = float(row["matchbook_back_odds"])
        return val if val > 1.0 else None
    book = str(row.get("best_book") or row.get("odds_source") or "").strip().lower()
    if book in ("matchbook", "mb", "exchange") and pd.notna(row.get("win_decimal")):
        val = float(row["win_decimal"])
        return val if val > 1.0 else None
    if pd.notna(row.get("live_odds_decimal")):
        val = float(row["live_odds_decimal"])
        return val if val > 1.0 else None
    if pd.notna(row.get("win_decimal")):
        val = float(row["win_decimal"])
        return val if val > 1.0 else None
    return None


def run_win_engine_calibration_circuit(database: Path) -> dict[str, Any]:
    """
    Evaluate variable field-size bounds and exchange market-beat contracts.
    Forces UNCALIBRATED when sample_n < N or any race block fails — fail-closed for public API.
    """
    from hibs_racing.models.win_engine_circuit import apply_calibration_circuit_breaker

    return apply_calibration_circuit_breaker(database)


def run_win_engine(
    cards: pd.DataFrame,
    *,
    database: Path | None = None,
    persist: bool = True,
) -> pd.DataFrame:
    """
    Two-step win engine:
    1) LightGBM LambdaRank athletic index (x_fund) grouped by race_id
    2) McFadden conditional logit softmax with live market velocity
    """
    if cards is None or cards.empty:
        return pd.DataFrame()

    cfg = load_config()
    db = database or db_path(cfg)
    ensure_win_engine_schema(db)

    frame = build_card_feature_frame(cards, database=db)
    card_cols = [c for c in cards.columns if c not in frame.columns and c != "runner_id"]
    if card_cols:
        frame = frame.merge(cards[["runner_id"] + card_cols], on="runner_id", how="left")

    scored = apply_scoring(frame)
    scored["x_fund"] = pd.to_numeric(scored.get("model_raw_score", scored.get("model_score")), errors="coerce").fillna(0.0)

    odds_col = "win_decimal" if "win_decimal" in scored.columns else "live_odds_decimal"
    if odds_col not in scored.columns:
        scored[odds_col] = np.nan
    scored["live_odds_decimal"] = pd.to_numeric(scored[odds_col], errors="coerce")
    missing_odds = scored["live_odds_decimal"].isna() | (scored["live_odds_decimal"] <= 1.0)
    if missing_odds.any():
        fallback = 1.0 / scored.groupby("race_id", sort=False)["x_fund"].transform(
            lambda s: np.exp(s - s.max()) / np.exp(s - s.max()).sum() if len(s) else 1.0
        )
        scored.loc[missing_odds, "live_odds_decimal"] = (1.0 / fallback[missing_odds]).clip(lower=1.01)

    mcfadden = mcfadden_conditional_logit(scored)
    mcfadden = _attach_place_probs(mcfadden)
    field_sizes = mcfadden.groupby("race_id", sort=False).size()

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    rows: list[dict[str, Any]] = []
    for _, row in mcfadden.iterrows():
        mb_odds = _resolve_matchbook_back_odds(row)
        race_id = row["race_id"]
        rows.append(
            {
                "runner_id": row["runner_id"],
                "race_id": race_id,
                "true_probability": float(row["true_probability"]),
                "fair_odds": float(row["fair_odds"]) if pd.notna(row["fair_odds"]) else None,
                "place_probability": float(row["place_probability"]) if pd.notna(row.get("place_probability")) else None,
                "live_odds_decimal": float(row["live_odds_decimal"]) if pd.notna(row["live_odds_decimal"]) else None,
                "matchbook_back_odds": mb_odds,
                "field_size": int(field_sizes.get(race_id, 1)),
                "x_fund": float(row["x_fund"]),
                "market_velocity": float(row["market_velocity"]) if pd.notna(row.get("market_velocity")) else None,
                "timestamp": now,
            }
        )

    if persist:
        with connect(db) as conn:
            upsert_predictions(conn, rows)
        run_win_engine_calibration_circuit(db)

    return mcfadden
