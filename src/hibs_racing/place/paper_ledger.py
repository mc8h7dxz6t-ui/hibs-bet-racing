from __future__ import annotations

import csv
import hashlib
import io
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from hibs_racing.config import db_path, load_config
from hibs_racing.entity.natural_key import courses_match, generate_natural_key
from hibs_racing.features.store import connect, init_db

_PLACE_TERMS_RE = re.compile(r"top\s*(\d+)", re.I)
_FRACTION_RE = re.compile(r"1/(\d+)")


@dataclass
class LedgerStats:
    open_bets: int
    settled_bets: int
    total_staked: float
    settled_staked: float
    total_pnl: float
    place_hits: int
    place_misses: int
    win_hits: int
    strike_rate: float | None
    roi_pct: float | None
    value_pick_count: int
    value_pick_settled: int
    value_pick_hits: int
    value_pick_strike: float | None

    def to_dict(self) -> dict:
        return {
            "open_bets": self.open_bets,
            "settled_bets": self.settled_bets,
            "total_staked": round(self.total_staked, 2),
            "settled_staked": round(self.settled_staked, 2),
            "total_pnl": round(self.total_pnl, 2),
            "place_hits": self.place_hits,
            "place_misses": self.place_misses,
            "win_hits": self.win_hits,
            "strike_rate": round(self.strike_rate, 4) if self.strike_rate is not None else None,
            "place_hit_pct": round(self.strike_rate * 100, 1) if self.strike_rate is not None else None,
            "roi_pct": round(self.roi_pct, 2) if self.roi_pct is not None else None,
            "value_pick_count": self.value_pick_count,
            "value_pick_settled": self.value_pick_settled,
            "value_pick_hits": self.value_pick_hits,
            "value_pick_strike": round(self.value_pick_strike, 4) if self.value_pick_strike is not None else None,
            "value_pick_strike_pct": round(self.value_pick_strike * 100, 1) if self.value_pick_strike is not None else None,
        }


def _parse_place_terms(text: str | None, *, default_places: int = 3, default_fraction: float = 0.25) -> tuple[int, float]:
    if not text:
        return default_places, default_fraction
    places = default_places
    fraction = default_fraction
    m = _PLACE_TERMS_RE.search(text)
    if m:
        places = int(m.group(1))
    m = _FRACTION_RE.search(text)
    if m:
        fraction = 1.0 / int(m.group(1))
    return places, fraction


def _each_way_pnl(
    *,
    finish_pos: int | None,
    bet_type: str,
    stake: float,
    win_decimal: float | None,
    place_fraction: float,
    places: int,
) -> tuple[float, str]:
    if finish_pos is None or finish_pos <= 0:
        return 0.0, "open"
    win = float(win_decimal or 0)
    if bet_type == "each_way" and win > 1:
        win_stake = stake * 0.5
        place_stake = stake * 0.5
        place_odds = 1.0 + (win - 1.0) * place_fraction
        if finish_pos == 1:
            return win_stake * win + place_stake * place_odds - stake, "won"
        if finish_pos <= places:
            return place_stake * place_odds - stake, "placed"
        return -stake, "lost"
    if bet_type == "place":
        place_odds = 1.0 + (win - 1.0) * place_fraction if win > 1 else 2.0
        if finish_pos <= places:
            return stake * place_odds - stake, "placed"
        return -stake, "lost"
    if finish_pos == 1 and win > 1:
        return stake * win - stake, "won"
    return -stake, "lost"


def _horse_slug(name: str) -> str:
    return name.lower().strip().replace(" ", "_")


def _normalize_horse(name: str) -> str:
    return re.sub(r"\s+", " ", name.lower().strip())


def _runner_slug_from_id(runner_id: str) -> str:
    return runner_id.split(":", 1)[-1] if ":" in runner_id else runner_id


def _upcoming_context(conn, runner_id: str) -> dict[str, str | None]:
    row = conn.execute(
        """
        SELECT card_date, course, off_time, horse_name, race_natural_key
        FROM upcoming_runners WHERE runner_id = ?
        """,
        (runner_id,),
    ).fetchone()
    if not row:
        return {}
    keys = ("card_date", "course", "off_time", "horse_name", "race_natural_key")
    return {k: (str(v) if v is not None else None) for k, v in zip(keys, row, strict=True)}


def _runners_context(conn, race_id: str, runner_id: str) -> dict[str, str | None]:
    """Fallback when upcoming_runners row was replaced — use ingested results spine."""
    slug = _runner_slug_from_id(runner_id)
    race_row = conn.execute(
        """
        SELECT race_date, course, off_time, race_natural_key
        FROM runners WHERE race_id = ? ORDER BY finish_pos IS NULL, runner_id LIMIT 1
        """,
        (race_id,),
    ).fetchone()
    horse_name = None
    for (horse_id,) in conn.execute(
        "SELECT horse_id FROM runners WHERE race_id = ? AND finish_pos IS NOT NULL",
        (race_id,),
    ).fetchall():
        if horse_id and _horse_slug(str(horse_id)) == slug:
            horse_name = str(horse_id)
            break
    if not horse_name:
        for (horse_id,) in conn.execute(
            "SELECT horse_id FROM runners WHERE race_id = ?",
            (race_id,),
        ).fetchall():
            if horse_id and _horse_slug(str(horse_id)) == slug:
                horse_name = str(horse_id)
                break
    if not race_row and not horse_name:
        return {}
    race_date, course, off_time, race_natural_key = race_row or (None, None, None, None)
    return {
        "card_date": str(race_date) if race_date else None,
        "course": str(course) if course else None,
        "off_time": str(off_time) if off_time else None,
        "horse_name": horse_name,
        "race_natural_key": str(race_natural_key) if race_natural_key else None,
    }


def _merge_context(*parts: dict[str, str | None]) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for part in parts:
        for key, val in part.items():
            if val and not out.get(key):
                out[key] = val
    return out


def _resolve_bet_context(
    conn,
    *,
    race_id: str,
    runner_id: str,
    card_date: str | None = None,
    horse_name: str | None = None,
    course: str | None = None,
    off_time: str | None = None,
    race_natural_key: str | None = None,
) -> dict[str, str | None]:
    ctx = _merge_context(
        {
            "card_date": card_date,
            "horse_name": horse_name,
            "course": course,
            "off_time": off_time,
            "race_natural_key": race_natural_key,
        },
        _upcoming_context(conn, runner_id),
        _runners_context(conn, race_id, runner_id),
    )
    return ctx


def _backfill_open_paper_context(conn) -> int:
    """Persist race context on open forward bets so settlement survives card refresh."""
    rows = conn.execute(
        """
        SELECT bet_id, race_id, runner_id, card_date, course, off_time, horse_name, race_natural_key
        FROM paper_bets
        WHERE status = 'open' AND backtest = 0
        """
    ).fetchall()
    updated = 0
    for bet_id, race_id, runner_id, card_date, course, off_time, horse_name, race_natural_key in rows:
        if card_date and horse_name:
            continue
        ctx = _resolve_bet_context(
            conn,
            race_id=race_id,
            runner_id=runner_id,
            card_date=card_date,
            horse_name=horse_name,
            course=course,
            off_time=off_time,
            race_natural_key=race_natural_key,
        )
        if not ctx.get("card_date"):
            continue
        conn.execute(
            """
            UPDATE paper_bets SET
                card_date = COALESCE(card_date, ?),
                course = COALESCE(course, ?),
                off_time = COALESCE(off_time, ?),
                horse_name = COALESCE(horse_name, ?),
                race_natural_key = COALESCE(race_natural_key, ?)
            WHERE bet_id = ?
            """,
            (
                ctx.get("card_date"),
                ctx.get("course"),
                ctx.get("off_time"),
                ctx.get("horse_name"),
                ctx.get("race_natural_key"),
                bet_id,
            ),
        )
        updated += 1
    return updated


def _find_finish_pos(
    conn,
    *,
    race_id: str,
    card_date: str,
    horse_name: str | None,
    runner_id: str,
    course: str | None = None,
    off_time: str | None = None,
    race_natural_key: str | None = None,
) -> int | None:
    slug = runner_id.split(":", 1)[-1] if ":" in runner_id else _horse_slug(horse_name or "")
    target_name = _normalize_horse(horse_name) if horse_name else ""

    natural_key = race_natural_key or generate_natural_key(card_date, course, off_time)

    def _match_horse(rows: list[tuple]) -> int | None:
        for pos, horse in rows:
            if horse and _horse_slug(str(horse)) == slug:
                return int(pos)
        if target_name:
            for pos, horse in rows:
                if horse and _normalize_horse(str(horse)) == target_name:
                    return int(pos)
        return None

    # 1) Natural key — primary cross-source join
    if natural_key:
        rows = conn.execute(
            """
            SELECT finish_pos, horse_id FROM runners
            WHERE race_natural_key = ? AND finish_pos IS NOT NULL
            """,
            (natural_key,),
        ).fetchall()
        hit = _match_horse(rows)
        if hit is not None:
            return hit

    # 2) Same date + normalized course + time (runners may lack precomputed key)
    if course and off_time:
        nk = generate_natural_key(card_date, course, off_time)
        rows = conn.execute(
            """
            SELECT finish_pos, horse_id, course, off_time FROM runners
            WHERE race_date = ? AND finish_pos IS NOT NULL
            """,
            (card_date,),
        ).fetchall()
        filtered = [
            (pos, horse)
            for pos, horse, rcourse, rtime in rows
            if courses_match(course, rcourse)
            and generate_natural_key(card_date, rcourse, rtime) == nk
        ]
        hit = _match_horse(filtered)
        if hit is not None:
            return hit

    # 3) Legacy race_id match
    rows = conn.execute(
        """
        SELECT finish_pos, horse_id FROM runners
        WHERE race_id = ? AND race_date = ? AND finish_pos IS NOT NULL
        """,
        (race_id, card_date),
    ).fetchall()
    hit = _match_horse(rows)
    if hit is not None:
        return hit

    # 4) Horse + date + fuzzy course
    if course or horse_name:
        params: list[object] = [card_date]
        clauses = ["race_date = ?", "finish_pos IS NOT NULL"]
        sql = f"SELECT finish_pos, horse_id, course FROM runners WHERE {' AND '.join(clauses)}"
        for pos, horse, rcourse in conn.execute(sql, params).fetchall():
            if course and not courses_match(course, rcourse):
                continue
            if horse and (
                _horse_slug(str(horse)) == slug
                or (target_name and _normalize_horse(str(horse)) == target_name)
            ):
                return int(pos)
    return None


def bet_verification_hash(
    bet_id: str,
    created_at: str,
    runner_id: str,
    offered_win: float | None,
    stake_units: float,
) -> str:
    payload = f"{bet_id}|{created_at}|{runner_id}|{offered_win}|{stake_units}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _closing_sp_for_runner(
    conn,
    *,
    finish_pos: int,
    race_id: str,
    card_date: str,
    horse_name: str | None,
    runner_id: str,
    course: str | None = None,
    off_time: str | None = None,
    race_natural_key: str | None = None,
) -> float | None:
    """Best-effort SP decimal from ingested results for CLV audit."""
    slug = runner_id.split(":", 1)[-1] if ":" in runner_id else _horse_slug(horse_name or "")
    target_name = _normalize_horse(horse_name) if horse_name else ""
    natural_key = race_natural_key or generate_natural_key(card_date, course, off_time)

    def _sp_from_rows(rows: list[tuple]) -> float | None:
        for pos, horse, sp in rows:
            if int(pos) != finish_pos:
                continue
            if horse and (_horse_slug(str(horse)) == slug or (target_name and _normalize_horse(str(horse)) == target_name)):
                try:
                    val = float(sp)
                    return val if val > 1.0 else None
                except (TypeError, ValueError):
                    return None
        return None

    if natural_key:
        rows = conn.execute(
            """
            SELECT finish_pos, horse_id, sp_decimal FROM runners
            WHERE race_natural_key = ? AND finish_pos IS NOT NULL AND sp_decimal IS NOT NULL
            """,
            (natural_key,),
        ).fetchall()
        sp = _sp_from_rows(rows)
        if sp is not None:
            return sp

    rows = conn.execute(
        """
        SELECT finish_pos, horse_id, sp_decimal FROM runners
        WHERE race_id = ? AND race_date = ? AND finish_pos IS NOT NULL AND sp_decimal IS NOT NULL
        """,
        (race_id, card_date),
    ).fetchall()
    return _sp_from_rows(rows)


def _date_cutoff(days: int | None) -> str | None:
    if days is None:
        return None
    start = datetime.now(timezone.utc) - timedelta(days=max(1, int(days)))
    return start.replace(microsecond=0).isoformat()


def settle_paper_bets(database: Path | None = None) -> dict:
    """Match open paper bets to ingested results and record P&L."""
    import os

    cfg = load_config()
    db = database or db_path(cfg)
    paper_cfg = cfg.get("paper", {})
    default_places = int(paper_cfg.get("default_places", 3))
    default_fraction = float(paper_cfg.get("default_place_fraction", 0.25))
    settle_at_sp = os.environ.get("HIBS_RACING_SETTLE_AT_SP", "").strip().lower() in ("1", "true", "yes", "on")
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    settled = 0
    still_open = 0
    details: list[dict] = []

    init_db(db)
    with connect(db) as conn:
        _backfill_open_paper_context(conn)
        bets = conn.execute(
            """
            SELECT pb.bet_id, pb.race_id, pb.runner_id, pb.bet_type, pb.stake_units,
                   pb.offered_win, pb.place_terms,
                   COALESCE(pb.card_date, u.card_date) AS card_date,
                   COALESCE(pb.horse_name, u.horse_name) AS horse_name,
                   COALESCE(pb.course, u.course) AS course,
                   COALESCE(pb.off_time, u.off_time) AS off_time,
                   COALESCE(pb.race_natural_key, u.race_natural_key) AS race_natural_key
            FROM paper_bets pb
            LEFT JOIN upcoming_runners u ON u.runner_id = pb.runner_id
            WHERE pb.status = 'open'
            """
        ).fetchall()
        for bet in bets:
            bet_id, race_id, runner_id, bet_type, stake, offered_win, place_terms, card_date, horse_name, course, off_time, race_natural_key = bet
            ctx = _resolve_bet_context(
                conn,
                race_id=race_id,
                runner_id=runner_id,
                card_date=card_date,
                horse_name=horse_name,
                course=course,
                off_time=off_time,
                race_natural_key=race_natural_key,
            )
            card_date = ctx.get("card_date")
            horse_name = ctx.get("horse_name")
            course = ctx.get("course")
            off_time = ctx.get("off_time")
            race_natural_key = ctx.get("race_natural_key")
            if not card_date:
                still_open += 1
                continue
            finish_pos = _find_finish_pos(
                conn,
                race_id=race_id,
                card_date=card_date,
                horse_name=horse_name,
                runner_id=runner_id,
                course=course,
                off_time=off_time,
                race_natural_key=race_natural_key,
            )
            if finish_pos is None:
                still_open += 1
                continue
            places, fraction = _parse_place_terms(place_terms, default_places=default_places, default_fraction=default_fraction)
            closing_sp = _closing_sp_for_runner(
                conn,
                finish_pos=finish_pos,
                race_id=race_id,
                card_date=card_date,
                horse_name=horse_name,
                runner_id=runner_id,
                course=course,
                off_time=off_time,
                race_natural_key=race_natural_key,
            )
            settlement_source = "offered"
            settlement_win = float(offered_win) if offered_win else None
            if settle_at_sp and closing_sp and float(closing_sp) > 1.0:
                settlement_source = "sp"
                settlement_win = float(closing_sp)
            pnl, status = _each_way_pnl(
                finish_pos=finish_pos,
                bet_type=bet_type,
                stake=float(stake),
                win_decimal=settlement_win,
                place_fraction=fraction,
                places=places,
            )
            clv_beat = None
            if closing_sp and offered_win and float(offered_win) > float(closing_sp):
                clv_beat = 1
            elif closing_sp and offered_win:
                clv_beat = 0
            conn.execute(
                """
                UPDATE paper_bets
                SET status = ?, result_pnl = ?, settled_at = ?, finish_pos = ?,
                    closing_sp = ?, clv_beat = ?,
                    settlement_price_source = ?, settlement_win_decimal = ?
                WHERE bet_id = ?
                """,
                (
                    status,
                    pnl,
                    now,
                    finish_pos,
                    closing_sp,
                    clv_beat,
                    settlement_source,
                    settlement_win,
                    bet_id,
                ),
            )
            settled += 1
            details.append(
                {
                    "bet_id": bet_id,
                    "horse_name": horse_name,
                    "status": status,
                    "finish_pos": finish_pos,
                    "pnl": round(pnl, 2),
                }
            )
        conn.commit()
    stats = ledger_stats(db).to_dict()
    return {
        "settled": settled,
        "still_open": still_open,
        "details": details,
        "stats": stats,
    }


def load_ledger_rows(
    database: Path | None = None,
    *,
    limit: int = 200,
    days: int | None = None,
    backtest: bool | None = False,
) -> list[dict]:
    db = database or db_path(load_config())
    init_db(db)
    cutoff = _date_cutoff(days)
    bt_clause = ""
    if backtest is True:
        bt_clause = " AND pb.backtest = 1"
    elif backtest is False:
        bt_clause = " AND pb.backtest = 0"
    with connect(db) as conn:
        if cutoff:
            rows = conn.execute(
                f"""
                SELECT pb.bet_id, pb.race_id, pb.runner_id, pb.bet_type, pb.stake_units, pb.model_ev,
                       pb.offered_win, pb.offered_place, pb.place_terms, pb.status, pb.result_pnl,
                       pb.settled_at, pb.created_at, pb.is_value_pick, pb.finish_pos,
                       pb.closing_sp, pb.clv_beat, pb.verification_hash, pb.backtest,
                       pb.settlement_price_source, pb.settlement_win_decimal,
                       COALESCE(u.horse_name, pb.horse_name) AS horse_name,
                       COALESCE(u.course, pb.course) AS course,
                       COALESCE(u.off_time, pb.off_time) AS off_time,
                       COALESCE(u.card_date, pb.card_date) AS card_date
                FROM paper_bets pb
                LEFT JOIN upcoming_runners u ON u.runner_id = pb.runner_id
                WHERE pb.created_at >= ?{bt_clause}
                ORDER BY pb.created_at DESC
                LIMIT ?
                """,
                (cutoff, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                f"""
                SELECT pb.bet_id, pb.race_id, pb.runner_id, pb.bet_type, pb.stake_units, pb.model_ev,
                       pb.offered_win, pb.offered_place, pb.place_terms, pb.status, pb.result_pnl,
                       pb.settled_at, pb.created_at, pb.is_value_pick, pb.finish_pos,
                       pb.closing_sp, pb.clv_beat, pb.verification_hash, pb.backtest,
                       pb.settlement_price_source, pb.settlement_win_decimal,
                       COALESCE(u.horse_name, pb.horse_name) AS horse_name,
                       COALESCE(u.course, pb.course) AS course,
                       COALESCE(u.off_time, pb.off_time) AS off_time,
                       COALESCE(u.card_date, pb.card_date) AS card_date
                FROM paper_bets pb
                LEFT JOIN upcoming_runners u ON u.runner_id = pb.runner_id
                WHERE 1=1{bt_clause}
                ORDER BY pb.created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
    cols = [
        "bet_id", "race_id", "runner_id", "bet_type", "stake_units", "model_ev",
        "offered_win", "offered_place", "place_terms", "status", "result_pnl",
        "settled_at", "created_at", "is_value_pick", "finish_pos",
        "closing_sp", "clv_beat", "verification_hash", "backtest",
        "settlement_price_source", "settlement_win_decimal",
        "horse_name", "course", "off_time", "card_date",
    ]
    return [dict(zip(cols, row, strict=True)) for row in rows]


def paper_bet_status_by_runner(
    *,
    card_dates: list[str] | None = None,
    database: Path | None = None,
) -> dict[str, dict]:
    """Map runner_id → paper ledger row for today's card(s) and historical continuity."""
    db = database or db_path(load_config())
    init_db(db)
    clauses = ["pb.backtest = 0"]
    params: list[object] = []
    if card_dates:
        placeholders = ",".join("?" for _ in card_dates)
        clauses.append(f"(u.card_date IN ({placeholders}) OR pb.created_at >= date('now', '-30 day'))")
        params.extend(card_dates)
    where = " AND ".join(clauses)
    with connect(db) as conn:
        rows = conn.execute(
            f"""
            SELECT pb.runner_id, pb.status, pb.result_pnl, pb.is_value_pick, pb.settled_at, u.card_date
            FROM paper_bets pb
            LEFT JOIN upcoming_runners u ON u.runner_id = pb.runner_id
            WHERE {where}
            ORDER BY pb.created_at DESC
            """,
            params,
        ).fetchall()
    out: dict[str, dict] = {}
    for runner_id, status, pnl, is_val, settled_at, card_date in rows:
        rid = str(runner_id or "")
        if not rid or rid in out:
            continue
        out[rid] = {
            "status": str(status or "open"),
            "result_pnl": float(pnl) if pnl is not None else None,
            "is_value_pick": bool(int(is_val or 0)),
            "settled_at": settled_at,
            "card_date": card_date,
        }
    return out


def ledger_stats(database: Path | None = None, *, days: int | None = None, backtest: bool | None = False) -> LedgerStats:
    db = database or db_path(load_config())
    init_db(db)
    cutoff = _date_cutoff(days)
    bt_clause = ""
    if backtest is True:
        bt_clause = " AND backtest = 1"
    elif backtest is False:
        bt_clause = " AND backtest = 0"
    with connect(db) as conn:
        if cutoff:
            rows = conn.execute(
                f"SELECT status, stake_units, result_pnl, is_value_pick FROM paper_bets WHERE created_at >= ?{bt_clause}",
                (cutoff,),
            ).fetchall()
        else:
            rows = conn.execute(
                f"SELECT status, stake_units, result_pnl, is_value_pick FROM paper_bets WHERE 1=1{bt_clause}",
            ).fetchall()

    open_bets = settled = place_hits = place_misses = win_hits = 0
    value_pick_count = value_pick_settled = value_pick_hits = value_pick_misses = 0
    total_staked = settled_staked = total_pnl = 0.0

    for status, stake, pnl, is_value in rows:
        stake_f = float(stake or 0)
        total_staked += stake_f
        is_val = int(is_value or 0) == 1
        if is_val:
            value_pick_count += 1

        if status == "open":
            open_bets += 1
            continue

        settled += 1
        settled_staked += stake_f
        total_pnl += float(pnl or 0)

        placed = status in ("won", "placed")
        if placed:
            place_hits += 1
        elif status == "lost":
            place_misses += 1
        if status == "won":
            win_hits += 1

        if is_val:
            value_pick_settled += 1
            if placed:
                value_pick_hits += 1
            elif status == "lost":
                value_pick_misses += 1

    strike = place_hits / (place_hits + place_misses) if (place_hits + place_misses) else None
    roi = (total_pnl / settled_staked * 100) if settled_staked > 0 else None
    value_strike = (
        value_pick_hits / (value_pick_hits + value_pick_misses)
        if (value_pick_hits + value_pick_misses)
        else None
    )

    return LedgerStats(
        open_bets=open_bets,
        settled_bets=settled,
        total_staked=total_staked,
        settled_staked=settled_staked,
        total_pnl=total_pnl,
        place_hits=place_hits,
        place_misses=place_misses,
        win_hits=win_hits,
        strike_rate=strike,
        roi_pct=roi,
        value_pick_count=value_pick_count,
        value_pick_settled=value_pick_settled,
        value_pick_hits=value_pick_hits,
        value_pick_strike=value_strike,
    )



def export_ledger_csv(
    database: Path | None = None,
    *,
    days: int | None = 60,
    backtest: bool | None = False,
) -> str:
    rows = load_ledger_rows(database, limit=10_000, days=days, backtest=backtest)
    buf = io.StringIO()
    if not rows:
        return ""
    writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


OOS_LEDGER_COLUMNS = [
    "bet_id",
    "card_date",
    "off_time",
    "course",
    "horse_name",
    "runner_id",
    "race_id",
    "bet_type",
    "stake_units",
    "offered_win",
    "closing_sp",
    "each_way_pnl",
    "status",
    "finish_pos",
    "model_ev",
    "verification_hash",
    "created_at",
    "settled_at",
]


def export_oos_ledger_csv(
    database: Path | None = None,
    *,
    start: str | None = None,
    end: str | None = None,
) -> str:
    """Sanitized backtest ledger for Acquire data room (SHA-256 verifiable)."""
    db = database or db_path(load_config())
    init_db(db)
    clauses = ["pb.backtest = 1"]
    params: list[object] = []
    if start:
        clauses.append("u.card_date >= ?")
        params.append(start)
    if end:
        clauses.append("u.card_date <= ?")
        params.append(end)
    where = " AND ".join(clauses)
    with connect(db) as conn:
        rows = conn.execute(
            f"""
            SELECT pb.bet_id, u.card_date, u.off_time, u.course, u.horse_name,
                   pb.runner_id, pb.race_id, pb.bet_type, pb.stake_units,
                   pb.offered_win, pb.closing_sp, pb.result_pnl, pb.status,
                   pb.finish_pos, pb.model_ev, pb.verification_hash,
                   pb.created_at, pb.settled_at
            FROM paper_bets pb
            LEFT JOIN upcoming_runners u ON u.runner_id = pb.runner_id
            WHERE {where}
            ORDER BY u.card_date, u.off_time, pb.created_at
            """,
            params,
        ).fetchall()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(OOS_LEDGER_COLUMNS)
    for row in rows:
        writer.writerow(
            [
                row[0],
                row[1],
                row[2],
                row[3],
                row[4],
                row[5],
                row[6],
                row[7],
                row[8],
                row[9],
                row[10],
                round(float(row[11]), 2) if row[11] is not None else "",
                row[12],
                row[13],
                round(float(row[14]), 4) if row[14] is not None else "",
                row[15],
                row[16],
                row[17],
            ]
        )
    return buf.getvalue()


MASTER_LEDGER_COLUMNS = OOS_LEDGER_COLUMNS + ["sample_type"]


def export_master_ledger_csv(
    database: Path | None = None,
    *,
    start: str,
    end: str,
    train_end: str | None = None,
) -> str:
    """6-month+ master sheet with calibration vs OOS holdout label per row."""
    cfg = load_config()
    cutoff = train_end or cfg.get("backtest", {}).get("train_end", "2026-04-30")
    raw = export_oos_ledger_csv(database, start=start, end=end)
    if not raw.strip():
        return ""
    lines = raw.strip().splitlines()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(MASTER_LEDGER_COLUMNS)
    header = lines[0].split(",")
    card_idx = header.index("card_date") if "card_date" in header else 1
    for line in lines[1:]:
        if not line.strip():
            continue
        # Simple CSV parse — fields are not quoted with commas in our export
        cols = line.split(",")
        card_date = cols[card_idx] if len(cols) > card_idx else ""
        sample = "oos_holdout" if card_date > cutoff else "calibration"
        writer.writerow(cols + [sample])
    return buf.getvalue()


def record_paper_bet(
    race_id: str,
    runner_id: str,
    bet_type: str,
    stake_units: float,
    *,
    model_ev: float | None = None,
    offered_win: float | None = None,
    offered_place: float | None = None,
    place_terms: str | None = None,
    is_value_pick: bool = False,
    backtest: bool = False,
    created_at: str | None = None,
    database: Path | None = None,
    audit_extra: dict | None = None,
) -> str:
    import uuid

    db = database or db_path(load_config())
    init_db(db)
    with connect(db) as conn:
        existing = conn.execute(
            """
            SELECT bet_id, is_value_pick FROM paper_bets
            WHERE runner_id = ? AND race_id = ? AND backtest = ?
            LIMIT 1
            """,
            (runner_id, race_id, 1 if backtest else 0),
        ).fetchone()
        if existing:
            bet_id = str(existing[0])
            if is_value_pick and not int(existing[1] or 0):
                now = created_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
                vhash = bet_verification_hash(bet_id, now, runner_id, offered_win, stake_units)
                conn.execute(
                    """
                    UPDATE paper_bets SET
                        is_value_pick = 1,
                        model_ev = COALESCE(?, model_ev),
                        offered_win = COALESCE(?, offered_win),
                        offered_place = COALESCE(?, offered_place),
                        place_terms = COALESCE(?, place_terms),
                        verification_hash = ?
                    WHERE bet_id = ?
                    """,
                    (
                        model_ev,
                        offered_win,
                        offered_place,
                        place_terms,
                        vhash,
                        bet_id,
                    ),
                )
                conn.commit()
            return bet_id

    bet_id = str(uuid.uuid4())
    now = created_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    vhash = bet_verification_hash(bet_id, now, runner_id, offered_win, stake_units)
    ctx: dict[str, str | None] = {}
    with connect(db) as conn:
        ctx = _resolve_bet_context(conn, race_id=race_id, runner_id=runner_id)
    with connect(db) as conn:
        conn.execute(
            """
            INSERT INTO paper_bets (
                bet_id, race_id, runner_id, bet_type, stake_units,
                model_ev, offered_win, offered_place, place_terms, is_value_pick,
                verification_hash, backtest, created_at,
                card_date, course, off_time, horse_name, race_natural_key
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                bet_id,
                race_id,
                runner_id,
                bet_type,
                stake_units,
                model_ev,
                offered_win,
                offered_place,
                place_terms,
                1 if is_value_pick else 0,
                vhash,
                1 if backtest else 0,
                now,
                ctx.get("card_date"),
                ctx.get("course"),
                ctx.get("off_time"),
                ctx.get("horse_name"),
                ctx.get("race_natural_key"),
            ),
        )
        conn.commit()
    if not backtest and is_value_pick:
        try:
            from hibs_racing.institutional.ledger_events import append_ledger_event

            payload = {
                "bet_id": bet_id,
                "bet_type": bet_type,
                "stake_units": stake_units,
                "offered_win": offered_win,
                "model_ev": model_ev,
                "is_value_pick": True,
            }
            if audit_extra:
                payload["audit"] = audit_extra
            append_ledger_event(
                event_type="bet_placed",
                runner_id=runner_id,
                race_id=race_id,
                verification_hash=vhash,
                payload=payload,
                database=db,
            )
        except Exception as exc:
            import logging

            logging.getLogger(__name__).warning(
                "bet_placed ledger event failed for %s: %s", bet_id, exc
            )
    return bet_id
