"""Persist exchange top-of-book quotes and join official SP for execution audit."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from hibs_racing.config import db_path, load_config
from hibs_racing.features.store import connect, init_db


def exchange_spread_bps(back: float | None, lay: float | None) -> float | None:
    """Bid-ask width in basis points vs mid: (lay - back) / mid * 10_000."""
    if back is None or lay is None:
        return None
    try:
        b, la = float(back), float(lay)
    except (TypeError, ValueError):
        return None
    if b <= 1.0 or la <= 1.0 or la < b:
        return None
    mid = (b + la) / 2.0
    if mid <= 0:
        return None
    return round((la - b) / mid * 10_000.0, 2)


def slippage_bps(offered_back: float | None, closing_sp: float | None) -> float | None:
    """
    Shortening vs offered back hurts the backer: positive bps = worse effective price.
    (offered - sp) / sp * 10_000
    """
    if offered_back is None or closing_sp is None:
        return None
    try:
        off, sp = float(offered_back), float(closing_sp)
    except (TypeError, ValueError):
        return None
    if sp <= 1.0 or off <= 1.0:
        return None
    return round((off - sp) / sp * 10_000.0, 2)


def persist_exchange_quotes(
    odds: pd.DataFrame,
    *,
    poll_milestone: str = "intraday",
    polled_at: str | None = None,
    database: Path | None = None,
) -> dict:
    """
    Write one row per runner from an odds frame (Matchbook poll or refresh).
    Expects optional columns: back_price/back_liquidity/lay_price/lay_liquidity or win_decimal aliases.
    """
    if odds is None or odds.empty or "runner_id" not in odds.columns:
        return {"rows": 0, "poll_milestone": poll_milestone}

    ts = polled_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    db = database or db_path(load_config())
    init_db(db)
    rows = 0
    with connect(db) as conn:
        for rec in odds.to_dict(orient="records"):
            rid = str(rec.get("runner_id") or "")
            if not rid:
                continue
            back = rec.get("back_price")
            if back is None:
                back = rec.get("win_decimal")
            lay = rec.get("lay_price")
            spread = rec.get("exchange_spread_bps")
            if spread is None:
                spread = exchange_spread_bps(back, lay)
            conn.execute(
                """
                INSERT OR REPLACE INTO exchange_quotes (
                    runner_id, timestamp, odds_source, poll_milestone, card_date, race_id,
                    back_price, back_liquidity, lay_price, lay_liquidity, exchange_spread_bps
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rid,
                    ts,
                    str(rec.get("odds_source") or "matchbook"),
                    poll_milestone,
                    rec.get("card_date"),
                    rec.get("race_id"),
                    back,
                    rec.get("back_liquidity"),
                    lay,
                    rec.get("lay_liquidity"),
                    spread,
                ),
            )
            rows += 1
        conn.commit()
    return {"rows": rows, "poll_milestone": poll_milestone, "timestamp": ts}


def quote_coverage_ratio(
    odds: pd.DataFrame | None,
    *,
    card_runners: int,
) -> float | None:
    if not card_runners:
        return None
    priced = 0 if odds is None or odds.empty else int(odds["runner_id"].nunique())
    return round(priced / card_runners, 4)


def upsert_value_pick_quotes(
    *,
    runner_id: str,
    card_date: str,
    race_id: str | None,
    poll_milestone: str,
    back_price: float | None,
    spread_bps: float | None = None,
    liquidity: float | None = None,
    polled_at: str | None = None,
    database: Path | None = None,
) -> None:
    """Merge latest poll into value_pick_execution for a flagged runner."""
    db = database or db_path(load_config())
    init_db(db)
    ts = polled_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    with connect(db) as conn:
        if poll_milestone == "baseline":
            conn.execute(
                """
                INSERT INTO value_pick_execution (
                    runner_id, card_date, race_id, baseline_back, baseline_ts,
                    spread_bps_at_baseline, liquidity_at_baseline
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(runner_id, card_date) DO UPDATE SET
                    race_id = COALESCE(excluded.race_id, value_pick_execution.race_id),
                    baseline_back = excluded.baseline_back,
                    baseline_ts = excluded.baseline_ts,
                    spread_bps_at_baseline = excluded.spread_bps_at_baseline,
                    liquidity_at_baseline = excluded.liquidity_at_baseline
                """,
                (runner_id, card_date, race_id, back_price, ts, spread_bps, liquidity),
            )
        elif poll_milestone == "pre_race_30m":
            conn.execute(
                """
                INSERT INTO value_pick_execution (runner_id, card_date, race_id, pre_race_30m_back, pre_race_30m_ts)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(runner_id, card_date) DO UPDATE SET
                    pre_race_30m_back = excluded.pre_race_30m_back,
                    pre_race_30m_ts = excluded.pre_race_30m_ts
                """,
                (runner_id, card_date, race_id, back_price, ts),
            )
        conn.commit()


def sync_value_picks_from_scored(
    scored: pd.DataFrame,
    *,
    poll_milestone: str,
    database: Path | None = None,
) -> int:
    """Update value_pick_execution rows for production value picks after a poll."""
    if scored.empty or "value_flag" not in scored.columns:
        return 0
    picks = scored[scored["value_flag"] == 1]
    n = 0
    for rec in picks.to_dict(orient="records"):
        upsert_value_pick_quotes(
            runner_id=str(rec["runner_id"]),
            card_date=str(rec.get("card_date") or ""),
            race_id=str(rec.get("race_id") or "") or None,
            poll_milestone=poll_milestone,
            back_price=rec.get("win_decimal"),
            spread_bps=rec.get("exchange_spread_bps"),
            liquidity=rec.get("back_liquidity"),
            database=database,
        )
        n += 1
    return n


def join_sp_to_value_picks(
    *,
    card_dates: list[str] | None = None,
    days: int | None = 14,
    database: Path | None = None,
) -> dict:
    """Post-race: attach official SP and slippage_bps to value_pick_execution + open paper bets."""
    db = database or db_path(load_config())
    init_db(db)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    joined = 0
    with connect(db) as conn:
        if card_dates:
            placeholders = ",".join("?" * len(card_dates))
            rows = conn.execute(
                f"""
                SELECT runner_id, card_date, race_id, baseline_back
                FROM value_pick_execution
                WHERE card_date IN ({placeholders}) AND closing_sp IS NULL
                """,
                card_dates,
            ).fetchall()
        elif days:
            rows = conn.execute(
                """
                SELECT runner_id, card_date, race_id, baseline_back
                FROM value_pick_execution
                WHERE closing_sp IS NULL
                  AND card_date >= date('now', ?)
                """,
                (f"-{int(days)} days",),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT runner_id, card_date, race_id, baseline_back FROM value_pick_execution WHERE closing_sp IS NULL"
            ).fetchall()

        for row in rows:
            runner_id, card_date, race_id, baseline_back = row
            sp_row = conn.execute(
                """
                SELECT sp_decimal FROM runners
                WHERE runner_id = ? AND race_date = ? AND sp_decimal IS NOT NULL
                LIMIT 1
                """,
                (runner_id, card_date),
            ).fetchone()
            if not sp_row:
                sp_row = conn.execute(
                    """
                    SELECT sp_decimal FROM runners
                    WHERE race_id = ? AND race_date = ? AND sp_decimal IS NOT NULL
                    LIMIT 1
                    """,
                    (race_id, card_date),
                ).fetchone()
            if not sp_row or sp_row[0] is None:
                continue
            sp = float(sp_row[0])
            slip = slippage_bps(baseline_back, sp)
            conn.execute(
                """
                UPDATE value_pick_execution
                SET closing_sp = ?, sp_captured_at = ?, slippage_bps = ?
                WHERE runner_id = ? AND card_date = ?
                """,
                (sp, now, slip, runner_id, card_date),
            )
            conn.execute(
                """
                UPDATE paper_bets
                SET closing_sp = ?, clv_beat = CASE
                    WHEN offered_win IS NOT NULL AND offered_win > ? THEN 1
                    WHEN offered_win IS NOT NULL THEN 0
                    ELSE clv_beat END
                WHERE runner_id = ? AND status != 'open'
                """,
                (sp, sp, runner_id),
            )
            joined += 1
        conn.commit()
    return {"joined": joined}


def dry_run_exchange_quotes(*, database: Path | None = None) -> dict:
    """Fetch Matchbook quotes for upcoming cards and persist without scoring."""
    from hibs_racing.cards.store import load_upcoming_runners
    from hibs_racing.odds.matchbook import fetch_matchbook_odds

    cards = load_upcoming_runners()
    if cards.empty:
        return {"ok": False, "error": "no upcoming cards"}
    odds, report = fetch_matchbook_odds(cards)
    if odds.empty:
        return {"ok": False, "error": "no quotes", "report": report.to_dict()}
    if "card_date" not in odds.columns and "card_date" in cards.columns:
        odds = odds.merge(cards[["runner_id", "card_date", "race_id"]], on="runner_id", how="left")
    persist = persist_exchange_quotes(odds, poll_milestone="dry_run")
    ratio = quote_coverage_ratio(odds, card_runners=len(cards))
    med_spread = None
    if "exchange_spread_bps" in odds.columns:
        s = odds["exchange_spread_bps"].dropna()
        med_spread = float(s.median()) if not s.empty else None
    card_venues = sorted(cards["course"].dropna().astype(str).unique().tolist()) if "course" in cards.columns else []
    return {
        "ok": True,
        "runners_on_card": len(cards),
        "runners_priced": report.runners_priced,
        "coverage_ratio": ratio,
        "median_spread_bps": med_spread,
        "persist": persist,
        "card_venues": card_venues[:20],
        "exchange_venues": report.to_dict().get("exchange_venues_on_card_dates", []),
        "report": report.to_dict(),
    }
