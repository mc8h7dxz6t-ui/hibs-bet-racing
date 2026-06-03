"""Retrospective backtest: replay historical GB/IRE cards, log value picks vs outcomes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from hibs_racing.cards.score_card import paper_log_value_picks, score_upcoming_cards
from hibs_racing.config import db_path, load_config
from hibs_racing.features.ranker_matrix import load_runner_frame
from hibs_racing.features.store import connect, init_db
from hibs_racing.place.paper_ledger import (
    _each_way_pnl,
    _parse_place_terms,
)

HISTORICAL_CARD_QUERY = """
SELECT
    runner_id,
    race_id,
    race_date AS card_date,
    off_time,
    course,
    region,
    race_type,
    race_class,
    TRIM(
        COALESCE(race_class, '') || CASE
            WHEN race_type IS NOT NULL AND TRIM(race_type) != ''
            THEN ' ' || race_type ELSE '' END
    ) AS race_name,
    going,
    field_size,
    distance_f,
    horse_id,
    horse_id AS horse_name,
    draw,
    official_rating,
    rpr,
    jockey,
    trainer,
    days_since_last_run,
    comment_norm AS card_comment,
    sp_decimal AS win_decimal,
    finish_pos,
    race_natural_key
FROM runners
WHERE race_date >= ?
  AND race_date <= ?
  AND finish_pos IS NOT NULL
  AND finish_pos > 0
ORDER BY race_date, off_time, race_id, runner_id
"""


@dataclass
class RetrospectiveReport:
    start_date: str
    end_date: str
    days_processed: int
    races_scored: int
    runners_scored: int
    value_picks_logged: int
    value_picks_settled: int
    top1_picks: int
    top1_wins: int
    stats: dict
    message: str
    oos_warning: str | None = None

    def to_dict(self) -> dict:
        top1_rate = self.top1_wins / self.top1_picks if self.top1_picks else None
        out = {
            "start_date": self.start_date,
            "end_date": self.end_date,
            "days_processed": self.days_processed,
            "races_scored": self.races_scored,
            "runners_scored": self.runners_scored,
            "value_picks_logged": self.value_picks_logged,
            "value_picks_settled": self.value_picks_settled,
            "top1_hit_rate": round(top1_rate, 4) if top1_rate is not None else None,
            "top1_wins": self.top1_wins,
            "top1_picks": self.top1_picks,
            "stats": self.stats,
            "message": self.message,
        }
        if self.oos_warning:
            out["oos_warning"] = self.oos_warning
        return out


def _date_range(*, months: int | None = None, start: str | None = None, end: str | None = None) -> tuple[str, str]:
    if start and end:
        return start, end
    end_dt = datetime.now(timezone.utc).date()
    if end:
        end_dt = datetime.strptime(end, "%Y-%m-%d").date()
    lookback_days = int(months or 3) * 30
    start_dt = end_dt - timedelta(days=lookback_days)
    if start:
        start_dt = datetime.strptime(start, "%Y-%m-%d").date()
    return start_dt.isoformat(), end_dt.isoformat()


def _load_historical_cards(db: Path, start: str, end: str) -> pd.DataFrame:
    init_db(db)
    with connect(db) as conn:
        frame = pd.read_sql_query(HISTORICAL_CARD_QUERY, conn, params=(start, end))
    if frame.empty:
        return frame
    frame["places"] = frame["field_size"].apply(lambda n: min(3, int(n)) if pd.notna(n) and int(n) > 0 else 3)
    frame["place_fraction"] = 0.25
    return frame


def _clear_backtest_ledger(db: Path) -> int:
    init_db(db)
    with connect(db) as conn:
        cur = conn.execute("DELETE FROM paper_bets WHERE backtest = 1")
        conn.commit()
        return int(cur.rowcount)


def _upsert_upcoming_runner(conn, rec: dict) -> None:
    conn.execute(
        """
        INSERT INTO upcoming_runners (
            runner_id, race_id, card_date, off_time, course, region, race_type,
            race_class, going, field_size, distance_f, place_fraction, places,
            horse_id, horse_name, draw, official_rating, rpr, jockey, trainer,
            days_since_last_run, card_comment, win_decimal, race_natural_key,
            source, fetched_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(runner_id) DO UPDATE SET
            card_date = excluded.card_date,
            horse_name = excluded.horse_name,
            course = excluded.course,
            off_time = excluded.off_time,
            win_decimal = excluded.win_decimal
        """,
        (
            rec["runner_id"],
            rec["race_id"],
            rec["card_date"],
            rec.get("off_time"),
            rec.get("course"),
            rec.get("region") or "GB",
            rec.get("race_type"),
            rec.get("race_class"),
            rec.get("going"),
            int(rec["field_size"]) if pd.notna(rec.get("field_size")) else None,
            rec.get("distance_f"),
            float(rec.get("place_fraction") or 0.25),
            int(rec.get("places") or 3),
            rec.get("horse_id"),
            rec.get("horse_name") or rec.get("horse_id"),
            int(rec["draw"]) if pd.notna(rec.get("draw")) else None,
            int(rec["official_rating"]) if pd.notna(rec.get("official_rating")) else None,
            int(rec["rpr"]) if pd.notna(rec.get("rpr")) else None,
            rec.get("jockey"),
            rec.get("trainer"),
            int(rec["days_since_last_run"]) if pd.notna(rec.get("days_since_last_run")) else None,
            rec.get("card_comment"),
            float(rec["win_decimal"]) if pd.notna(rec.get("win_decimal")) else None,
            rec.get("race_natural_key"),
            "backtest",
            datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        ),
    )


def _settle_backtest_bets(db: Path, scored: pd.DataFrame, outcomes: pd.DataFrame) -> int:
    """Settle backtest value picks immediately using known finish positions."""
    cfg = load_config()
    paper_cfg = cfg.get("paper", {})
    default_places = int(paper_cfg.get("default_places", 3))
    default_fraction = float(paper_cfg.get("default_place_fraction", 0.25))
    outcome_map = outcomes.set_index("runner_id")["finish_pos"].to_dict()
    settled = 0
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    with connect(db) as conn:
        for rec in scored[scored["value_flag"] == 1].to_dict(orient="records"):
            runner_id = rec["runner_id"]
            finish_pos = outcome_map.get(runner_id)
            if finish_pos is None:
                continue
            row = conn.execute(
                "SELECT bet_id, stake_units, offered_win, place_terms FROM paper_bets WHERE runner_id = ? AND backtest = 1",
                (runner_id,),
            ).fetchone()
            if not row:
                continue
            bet_id, stake, offered_win, place_terms = row
            places, fraction = _parse_place_terms(
                place_terms, default_places=default_places, default_fraction=default_fraction
            )
            pnl, status = _each_way_pnl(
                finish_pos=int(finish_pos),
                bet_type="each_way",
                stake=float(stake),
                win_decimal=offered_win,
                place_fraction=fraction,
                places=places,
            )
            closing_sp = float(rec["win_decimal"]) if pd.notna(rec.get("win_decimal")) else None
            clv_beat = None
            if closing_sp and offered_win and float(offered_win) >= closing_sp:
                clv_beat = 1 if float(offered_win) > closing_sp else 0
            conn.execute(
                """
                UPDATE paper_bets
                SET status = ?, result_pnl = ?, settled_at = ?, finish_pos = ?,
                    closing_sp = ?, clv_beat = ?
                WHERE bet_id = ?
                """,
                (status, pnl, now, int(finish_pos), closing_sp, clv_beat, bet_id),
            )
            settled += 1
        conn.commit()
    return settled


def run_retrospective_backtest(
    *,
    months: int = 3,
    start: str | None = None,
    end: str | None = None,
    database: Path | None = None,
    replace: bool = True,
    min_sp: float = 1.01,
) -> RetrospectiveReport:
    """
    Walk historical race days with point-in-time features.
    Uses closing SP as offered win odds; logs + settles value picks to paper_bets (backtest=1).
    """
    cfg = load_config()
    db = database or db_path(cfg)
    init_db(db)
    start_date, end_date = _date_range(months=months, start=start, end=end)

    cards = _load_historical_cards(db, start_date, end_date)
    if cards.empty:
        return RetrospectiveReport(
            start_date,
            end_date,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            {},
            f"No historical runners between {start_date} and {end_date}. Run ingest-raceform first.",
        )

    if replace:
        _clear_backtest_ledger(db)

    cfg = load_config()
    train_end = cfg.get("backtest", {}).get("train_end")
    oos_warning = None
    if train_end and start_date <= train_end:
        oos_warning = (
            f"Dates overlap ranker training period (train_end={train_end}). "
            "Use --start after train_end for out-of-sample results."
        )

    full_hist = load_runner_frame(db)
    stake = float(cfg.get("paper", {}).get("default_stake", 1.0))
    dates = sorted(cards["card_date"].unique())
    value_logged = 0
    value_settled = 0
    races_scored = 0
    runners_scored = 0
    top1_picks = 0
    top1_wins = 0

    for card_date in dates:
        day = cards[cards["card_date"] == card_date].copy()
        day = day[day["win_decimal"].notna() & (day["win_decimal"] >= min_sp)]
        if day.empty:
            continue

        odds = day[["runner_id", "win_decimal", "place_fraction", "places"]].copy()
        outcomes = day[["runner_id", "finish_pos", "win_decimal"]].copy()
        score_input = day.drop(columns=["finish_pos"], errors="ignore")

        scored = score_upcoming_cards(
            score_input,
            database=db,
            odds=odds,
            persist=False,
            hist_frame=full_hist,
            hist_before_date=str(card_date),
        )
        races_scored += scored["race_id"].nunique()
        runners_scored += len(scored)

        for _, race in scored.groupby("race_id", sort=False):
            top = race.sort_values("model_score", ascending=False).head(1)
            if top.empty:
                continue
            top1_picks += 1
            rid = top.iloc[0]["runner_id"]
            if int(outcomes.loc[outcomes["runner_id"] == rid, "finish_pos"].iloc[0]) == 1:
                top1_wins += 1

        bet_ids = paper_log_value_picks(
            scored,
            stake=stake,
            backtest=True,
            created_at=f"{card_date}T06:00:00+00:00",
        )
        value_logged += len(bet_ids)

        with connect(db) as conn:
            for rec in day.to_dict(orient="records"):
                _upsert_upcoming_runner(conn, rec)
            conn.commit()

        value_settled += _settle_backtest_bets(db, scored, outcomes)

    stats = _backtest_ledger_stats(db)
    msg = (
        f"Retrospective backtest {start_date} → {end_date}: "
        f"{value_logged} value picks logged, {value_settled} settled."
    )
    return RetrospectiveReport(
        start_date=start_date,
        end_date=end_date,
        days_processed=len(dates),
        races_scored=races_scored,
        runners_scored=runners_scored,
        value_picks_logged=value_logged,
        value_picks_settled=value_settled,
        top1_picks=top1_picks,
        top1_wins=top1_wins,
        stats=stats,
        message=msg,
        oos_warning=oos_warning,
    )


def export_oos_ledger(
    *,
    start: str,
    end: str,
    output_path: Path | None = None,
    database: Path | None = None,
) -> Path:
    from hibs_racing.config import ROOT
    from hibs_racing.place.paper_ledger import export_oos_ledger_csv

    csv_text = export_oos_ledger_csv(database, start=start, end=end)
    if not csv_text.strip() or csv_text.count("\n") < 1:
        raise ValueError("No backtest ledger rows to export for the requested date range.")
    out = output_path or (ROOT / "exports" / "Hibs_Racing_OOS_PhaseA_May2026_TrackRecord.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(csv_text, encoding="utf-8")
    return out


def write_master_ledger(
    *,
    start: str,
    end: str,
    output_path: Path | None = None,
    database: Path | None = None,
) -> tuple[Path, dict]:
    from hibs_racing.config import ROOT
    from hibs_racing.place.paper_ledger import export_master_ledger_csv

    db = database or db_path(load_config())
    csv_text = export_master_ledger_csv(db, start=start, end=end)
    if not csv_text.strip():
        raise ValueError("No backtest rows for master export in the requested range.")
    out = output_path or (ROOT / "exports" / "Hibs_Racing_Master_6Month_TrackRecord.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(csv_text, encoding="utf-8")
    rows = max(0, csv_text.count("\n") - 1)
    cal = oos = 0
    for line in csv_text.strip().splitlines()[1:]:
        if line.endswith(",oos_holdout"):
            oos += 1
        elif line.endswith(",calibration"):
            cal += 1
    return out, {
        "export_path": str(out),
        "total_rows": rows,
        "calibration_rows": cal,
        "oos_holdout_rows": oos,
        "start": start,
        "end": end,
    }


def _backtest_ledger_stats(db: Path) -> dict:
    init_db(db)
    with connect(db) as conn:
        rows = conn.execute(
            "SELECT status, stake_units, result_pnl, is_value_pick FROM paper_bets WHERE backtest = 1",
        ).fetchall()
    settled_staked = total_pnl = 0.0
    place_hits = place_misses = 0
    for status, stake, pnl, _ in rows:
        if status == "open":
            continue
        settled_staked += float(stake or 0)
        total_pnl += float(pnl or 0)
        if status in ("won", "placed"):
            place_hits += 1
        elif status == "lost":
            place_misses += 1
    roi = (total_pnl / settled_staked * 100) if settled_staked > 0 else None
    strike = place_hits / (place_hits + place_misses) if (place_hits + place_misses) else None
    return {
        "backtest_bets": len(rows),
        "settled": place_hits + place_misses,
        "place_hit_rate": round(strike, 4) if strike is not None else None,
        "roi_pct": round(roi, 2) if roi is not None else None,
        "total_pnl": round(total_pnl, 2),
    }
