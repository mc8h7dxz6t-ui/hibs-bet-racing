"""Extended out-of-sample backtest for the McFadden win engine."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from hibs_racing.backtest.retrospective import _date_range, _load_historical_cards
from hibs_racing.config import db_path, load_config
from hibs_racing.features.store import connect, init_db
from hibs_racing.models.win_engine_circuit import evaluate_calibration_circuit
from hibs_racing.models.win_engine_config import win_brier_pass_max
from hibs_racing.models.win_engine_service import run_win_engine
from hibs_racing.models.win_engine_store import ensure_win_engine_schema, update_calibration_state


def _safe_log_loss(prob: float, won: int) -> float:
    p = min(max(float(prob), 1e-9), 1.0 - 1e-9)
    return -(won * math.log(p) + (1 - won) * math.log(1.0 - p))


def _market_implied_prob(sp: float) -> float:
    if sp is None or sp <= 1.0 or not np.isfinite(sp):
        return np.nan
    raw = 1.0 / float(sp)
    return min(max(raw, 1e-9), 1.0 - 1e-9)


def _calibration_bins(rows: pd.DataFrame, *, n_bins: int = 10) -> list[dict[str, Any]]:
    if rows.empty:
        return []
    chunk = rows.dropna(subset=["true_probability", "won"]).copy()
    if chunk.empty:
        return []
    chunk["bin"] = pd.cut(chunk["true_probability"], bins=n_bins, labels=False)
    out: list[dict[str, Any]] = []
    for bin_id, group in chunk.groupby("bin", sort=True):
        if pd.isna(bin_id):
            continue
        out.append(
            {
                "bin": int(bin_id),
                "n": int(len(group)),
                "mean_pred": round(float(group["true_probability"].mean()), 4),
                "actual_rate": round(float(group["won"].mean()), 4),
            }
        )
    return out


@dataclass
class WinEngineBacktestReport:
    start_date: str
    end_date: str
    days_processed: int
    races: int
    runners: int
    mean_brier: float | None
    market_brier: float | None
    brier_skill: float | None
    mean_log_loss: float | None
    top1_picks: int
    top1_wins: int
    top1_hit_rate: float | None
    place_brier: float | None
    value_bets: int = 0
    value_wins: int = 0
    value_roi_units: float = 0.0
    calibration_bins: list[dict[str, Any]] = field(default_factory=list)
    monthly: list[dict[str, Any]] = field(default_factory=list)
    brier_threshold: float = 0.185
    brier_pass: bool = False
    oos_warning: str | None = None
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "start_date": self.start_date,
            "end_date": self.end_date,
            "days_processed": self.days_processed,
            "races": self.races,
            "runners": self.runners,
            "mean_brier": self.mean_brier,
            "market_brier": self.market_brier,
            "brier_skill": self.brier_skill,
            "mean_log_loss": self.mean_log_loss,
            "top1_picks": self.top1_picks,
            "top1_wins": self.top1_wins,
            "top1_hit_rate": self.top1_hit_rate,
            "place_brier": self.place_brier,
            "value_bets": self.value_bets,
            "value_wins": self.value_wins,
            "value_roi_units": round(self.value_roi_units, 4),
            "calibration_bins": self.calibration_bins,
            "monthly": self.monthly,
            "brier_threshold": self.brier_threshold,
            "brier_pass": self.brier_pass,
            "oos_warning": self.oos_warning,
            "message": self.message,
        }


def run_win_engine_backtest(
    *,
    months: int = 6,
    start: str | None = None,
    end: str | None = None,
    database: Path | None = None,
    min_sp: float = 1.01,
    extended: bool = True,
    seed_calibration: bool = False,
    persist_predictions: bool = False,
) -> WinEngineBacktestReport:
    """
    Walk settled historical cards day-by-day; score with McFadden win engine (SP as pre-race odds).

    extended=True adds calibration deciles, monthly Brier, and flat-win value ROI (fair < SP).
    seed_calibration writes aggregate stats into win_engine_calibration (does not flip HIBS_WIN_ENGINE_ACTIVE).
    """
    cfg = load_config()
    db = database or db_path(cfg)
    init_db(db)
    ensure_win_engine_schema(db)

    start_date, end_date = _date_range(months=months, start=start, end=end)
    cards = _load_historical_cards(db, start_date, end_date)
    if cards.empty:
        return WinEngineBacktestReport(
            start_date,
            end_date,
            0,
            0,
            0,
            None,
            None,
            None,
            None,
            0,
            0,
            None,
            None,
            message=f"No historical runners between {start_date} and {end_date}. Run ingest-raceform first.",
        )

    train_end = (cfg.get("backtest") or {}).get("train_end")
    oos_warning = None
    if train_end and start_date <= str(train_end):
        oos_warning = (
            f"Dates overlap ranker training period (train_end={train_end}). "
            f"Use --start after {train_end} for out-of-sample win-engine results."
        )

    threshold = win_brier_pass_max()
    all_rows: list[dict[str, Any]] = []
    days_processed = 0
    races_total = 0
    top1_picks = 0
    top1_wins = 0
    value_bets = 0
    value_wins = 0
    value_roi = 0.0

    for card_date in sorted(cards["card_date"].unique()):
        day = cards[cards["card_date"] == card_date].copy()
        day = day[day["win_decimal"].notna() & (pd.to_numeric(day["win_decimal"], errors="coerce") >= min_sp)]
        if day.empty:
            continue

        score_input = day.drop(columns=["finish_pos"], errors="ignore")
        try:
            scored = run_win_engine(score_input, database=db, persist=persist_predictions)
        except Exception:
            continue
        if scored is None or scored.empty:
            continue

        days_processed += 1
        outcomes = day[["runner_id", "finish_pos", "win_decimal"]].copy()
        merged = scored.drop(columns=["finish_pos", "win_decimal"], errors="ignore").merge(
            outcomes,
            on="runner_id",
            how="inner",
        )
        if merged.empty:
            continue

        for race_id, group in merged.groupby("race_id", sort=False):
            races_total += 1
            if group.empty:
                continue
            top = group.loc[group["true_probability"].idxmax()]
            top1_picks += 1
            if int(top["finish_pos"]) == 1:
                top1_wins += 1

        for _, row in merged.iterrows():
            won = 1 if int(row["finish_pos"]) == 1 else 0
            prob = float(row["true_probability"])
            brier = (prob - won) ** 2
            sp = float(row["win_decimal"])
            mkt = _market_implied_prob(sp)
            mkt_brier = (mkt - won) ** 2 if np.isfinite(mkt) else None
            place_prob = row.get("place_probability")
            place_brier = None
            if place_prob is not None and pd.notna(place_prob):
                placed = 1 if int(row["finish_pos"]) <= 3 else 0
                place_brier = (float(place_prob) - placed) ** 2

            fair = row.get("fair_odds")
            if extended and fair is not None and pd.notna(fair) and float(fair) < sp:
                value_bets += 1
                if won:
                    value_wins += 1
                    value_roi += sp - 1.0
                else:
                    value_roi -= 1.0

            all_rows.append(
                {
                    "card_date": card_date,
                    "race_id": row["race_id"],
                    "runner_id": row["runner_id"],
                    "true_probability": prob,
                    "won": won,
                    "brier": brier,
                    "market_brier": mkt_brier,
                    "log_loss": _safe_log_loss(prob, won),
                    "place_brier": place_brier,
                }
            )

    if not all_rows:
        return WinEngineBacktestReport(
            start_date,
            end_date,
            days_processed,
            races_total,
            0,
            None,
            None,
            None,
            None,
            top1_picks,
            top1_wins,
            (top1_wins / top1_picks) if top1_picks else None,
            None,
            oos_warning=oos_warning,
            message="Historical cards found but win engine produced no scored rows.",
        )

    frame = pd.DataFrame(all_rows)
    mean_brier = float(frame["brier"].mean())
    market_brier = float(frame["market_brier"].dropna().mean()) if frame["market_brier"].notna().any() else None
    brier_skill = (market_brier - mean_brier) if market_brier is not None else None
    mean_log_loss = float(frame["log_loss"].mean())
    place_brier = float(frame["place_brier"].dropna().mean()) if frame["place_brier"].notna().any() else None
    hit_rate = top1_wins / top1_picks if top1_picks else None
    brier_pass = mean_brier <= threshold and len(frame) >= 100

    monthly: list[dict[str, Any]] = []
    calibration_bins: list[dict[str, Any]] = []
    if extended:
        calibration_bins = _calibration_bins(frame)
        frame["month"] = frame["card_date"].astype(str).str.slice(0, 7)
        for month, group in frame.groupby("month", sort=True):
            monthly.append(
                {
                    "month": month,
                    "runners": int(len(group)),
                    "mean_brier": round(float(group["brier"].mean()), 5),
                    "market_brier": round(float(group["market_brier"].dropna().mean()), 5)
                    if group["market_brier"].notna().any()
                    else None,
                    "top1_hit_rate": None,
                }
            )

    if seed_calibration:
        with connect(db) as conn:
            state = "CALIBRATED" if brier_pass else "UNCALIBRATED"
            update_calibration_state(
                conn,
                calibration_state=state,
                rolling_brier=mean_brier,
                sample_n=len(frame),
                races_in_window=races_total,
            )
        if persist_predictions:
            evaluate_calibration_circuit(db)

    if market_brier is not None:
        mkt_txt = f"{market_brier:.4f}"
    else:
        mkt_txt = "n/a"
    if hit_rate is not None:
        msg = (
            f"Win engine OOS backtest {start_date}..{end_date}: "
            f"Brier={mean_brier:.4f} (market={mkt_txt}), "
            f"top1={hit_rate:.1%} ({top1_wins}/{top1_picks}), n={len(frame)}"
        )
    else:
        msg = f"Win engine OOS backtest {start_date}..{end_date}: n={len(frame)}"

    return WinEngineBacktestReport(
        start_date=start_date,
        end_date=end_date,
        days_processed=days_processed,
        races=races_total,
        runners=len(frame),
        mean_brier=round(mean_brier, 5),
        market_brier=round(market_brier, 5) if market_brier is not None else None,
        brier_skill=round(brier_skill, 5) if brier_skill is not None else None,
        mean_log_loss=round(mean_log_loss, 5),
        top1_picks=top1_picks,
        top1_wins=top1_wins,
        top1_hit_rate=round(hit_rate, 4) if hit_rate is not None else None,
        place_brier=round(place_brier, 5) if place_brier is not None else None,
        value_bets=value_bets,
        value_wins=value_wins,
        value_roi_units=value_roi,
        calibration_bins=calibration_bins,
        monthly=monthly,
        brier_threshold=threshold,
        brier_pass=brier_pass,
        oos_warning=oos_warning,
        message=msg,
    )
