from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from datetime import datetime, timezone
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


def settle_paper_bets(database: Path | None = None) -> dict:
    """Match open paper bets to ingested results and record P&L."""
    cfg = load_config()
    db = database or db_path(cfg)
    paper_cfg = cfg.get("paper", {})
    default_places = int(paper_cfg.get("default_places", 3))
    default_fraction = float(paper_cfg.get("default_place_fraction", 0.25))
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    settled = 0
    still_open = 0
    details: list[dict] = []

    init_db(db)
    with connect(db) as conn:
        bets = conn.execute(
            """
            SELECT pb.bet_id, pb.race_id, pb.runner_id, pb.bet_type, pb.stake_units,
                   pb.offered_win, pb.place_terms, u.card_date, u.horse_name, u.course,
                   u.off_time, u.race_natural_key
            FROM paper_bets pb
            LEFT JOIN upcoming_runners u ON u.runner_id = pb.runner_id
            WHERE pb.status = 'open'
            """
        ).fetchall()
        for bet in bets:
            bet_id, race_id, runner_id, bet_type, stake, offered_win, place_terms, card_date, horse_name, course, off_time, race_natural_key = bet
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
            pnl, status = _each_way_pnl(
                finish_pos=finish_pos,
                bet_type=bet_type,
                stake=float(stake),
                win_decimal=offered_win,
                place_fraction=fraction,
                places=places,
            )
            conn.execute(
                """
                UPDATE paper_bets
                SET status = ?, result_pnl = ?, settled_at = ?, finish_pos = ?
                WHERE bet_id = ?
                """,
                (status, pnl, now, finish_pos, bet_id),
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


def load_ledger_rows(database: Path | None = None, *, limit: int = 200) -> list[dict]:
    db = database or db_path(load_config())
    init_db(db)
    with connect(db) as conn:
        rows = conn.execute(
            """
            SELECT pb.bet_id, pb.race_id, pb.runner_id, pb.bet_type, pb.stake_units, pb.model_ev,
                   pb.offered_win, pb.offered_place, pb.place_terms, pb.status, pb.result_pnl,
                   pb.settled_at, pb.created_at, pb.is_value_pick, pb.finish_pos,
                   u.horse_name, u.course, u.off_time, u.card_date
            FROM paper_bets pb
            LEFT JOIN upcoming_runners u ON u.runner_id = pb.runner_id
            ORDER BY pb.created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    cols = [
        "bet_id", "race_id", "runner_id", "bet_type", "stake_units", "model_ev",
        "offered_win", "offered_place", "place_terms", "status", "result_pnl",
        "settled_at", "created_at", "is_value_pick", "finish_pos",
        "horse_name", "course", "off_time", "card_date",
    ]
    return [dict(zip(cols, row, strict=True)) for row in rows]


def ledger_stats(database: Path | None = None) -> LedgerStats:
    db = database or db_path(load_config())
    init_db(db)
    with connect(db) as conn:
        rows = conn.execute(
            """
            SELECT status, stake_units, result_pnl, is_value_pick
            FROM paper_bets
            """
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


def build_tracker_dict(database: Path | None = None, *, limit: int = 200) -> dict:
    stats = ledger_stats(database).to_dict()
    rows = load_ledger_rows(database, limit=limit)
    return {
        "enabled": True,
        "methodology": {
            "lock_rule": "Paper bets logged at score time with model EV gates.",
            "settlement_rule": "Auto-settled via race natural key (date+course+time), then horse/course fallbacks.",
        },
        "stats": stats,
        "ledger_rows": rows,
        "ledger_count": len(rows),
        "third_party_note": "Paper ledger only — no live money. Settle via hibs-racing settle-paper after ingesting results.",
    }


def export_ledger_csv(database: Path | None = None) -> str:
    rows = load_ledger_rows(database, limit=10_000)
    buf = io.StringIO()
    if not rows:
        return ""
    writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
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
    database: Path | None = None,
) -> str:
    import uuid

    db = database or db_path(load_config())
    init_db(db)
    bet_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    with connect(db) as conn:
        conn.execute(
            """
            INSERT INTO paper_bets (
                bet_id, race_id, runner_id, bet_type, stake_units,
                model_ev, offered_win, offered_place, place_terms, is_value_pick, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                now,
            ),
        )
        conn.commit()
    return bet_id
