from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from hibs_racing.backtest.retrospective import _load_historical_cards
from hibs_racing.backtest.slippage_stress import apply_slippage_to_frame, default_slip_bps_list
from hibs_racing.backtest.snapshot_store import (
    load_snapshots,
    merge_upcoming_enrich,
    resolve_snapshot_config_hash,
    scoring_config_hash,
    snapshot_coverage,
    upsert_snapshots,
)
from hibs_racing.cards.actionability import apply_value_gates
from hibs_racing.cards.score_card import score_upcoming_cards
from hibs_racing.config import db_path, load_config
from hibs_racing.features.ranker_matrix import load_runner_frame
from hibs_racing.features.store import connect, init_db
from hibs_racing.place.paper_ledger import _each_way_pnl


@dataclass
class GateBenchmarkReport:
    start: str
    end: str
    card_days: int
    races: int
    runners: int
    none: dict[str, float | int | None]
    gate1: dict[str, float | int | None]
    gate2: dict[str, float | int | None]
    production: dict[str, float | int | None]
    delta_gate1_vs_none: dict[str, float | int | None]
    delta_gate2_vs_gate1: dict[str, float | int | None]
    delta_gate2_vs_none: dict[str, float | int | None]
    delta_production_vs_none: dict[str, float | int | None]
    delta_production_vs_gate2: dict[str, float | int | None]
    blocked_reasons_gate1: dict[str, int]
    blocked_reasons_gate2: dict[str, int]
    blocked_reasons_production: dict[str, int]
    slippage: dict[str, dict[str, float | int | None]] = field(default_factory=dict)
    snapshot_source: str = "scored"
    snapshot_config_hash: str | None = None
    message: str = ""

    def to_dict(self) -> dict:
        out = {
            "start": self.start,
            "end": self.end,
            "card_days": self.card_days,
            "races": self.races,
            "runners": self.runners,
            "none": self.none,
            "gate1": self.gate1,
            "gate2": self.gate2,
            "production": self.production,
            "delta_gate1_vs_none": self.delta_gate1_vs_none,
            "delta_gate2_vs_gate1": self.delta_gate2_vs_gate1,
            "delta_gate2_vs_none": self.delta_gate2_vs_none,
            "delta_production_vs_none": self.delta_production_vs_none,
            "delta_production_vs_gate2": self.delta_production_vs_gate2,
            "blocked_reasons_gate1": self.blocked_reasons_gate1,
            "blocked_reasons_gate2": self.blocked_reasons_gate2,
            "blocked_reasons_production": self.blocked_reasons_production,
            "snapshot_source": self.snapshot_source,
            "snapshot_config_hash": self.snapshot_config_hash,
            "message": self.message,
        }
        if self.slippage:
            out["slippage"] = self.slippage
        return out


def _historical_bounds(db: Path) -> tuple[str | None, str | None]:
    """Date bounds without init_db — read-only, ramdisk-safe."""
    from hibs_racing.backtest.db_resolve import open_backtest_connection

    try:
        conn = open_backtest_connection(db)
    except sqlite3.Error:
        try:
            init_db(db)
            conn = sqlite3.connect(str(db), timeout=30.0)
        except sqlite3.Error:
            return None, None
    try:
        row = conn.execute(
            """
            SELECT MIN(card_date), MAX(card_date)
            FROM scored_runner_snapshots
            WHERE card_date IS NOT NULL
            """
        ).fetchone()
        if row and row[0] and row[1]:
            return str(row[0]), str(row[1])
        row = conn.execute(
            """
            SELECT MIN(race_date), MAX(race_date)
            FROM runners
            WHERE finish_pos IS NOT NULL
              AND finish_pos > 0
              AND sp_decimal IS NOT NULL
            """
        ).fetchone()
        if not row:
            return None, None
        return row[0], row[1]
    except sqlite3.Error:
        return None, None
    finally:
        conn.close()


def _gate_configs(paper_cfg: dict, *, gate2_caps: bool = True) -> tuple[dict, dict]:
    gate1_cfg = deepcopy(paper_cfg)
    gate1_cfg["enforce_steam_gate"] = False
    gate1_cfg["min_data_quality_pct"] = None
    if isinstance(gate1_cfg.get("gate2"), dict):
        gate1_cfg["gate2"]["enabled"] = False
    gate2_cfg = deepcopy(paper_cfg)
    gate2_cfg["enforce_steam_gate"] = False
    gate2_cfg["min_data_quality_pct"] = None
    gate2_cfg.setdefault("gate2", {})
    gate2_cfg["gate2"]["enabled"] = True
    if not gate2_caps and isinstance(gate2_cfg["gate2"], dict):
        gate2_cfg["gate2"]["max_value_per_race"] = None
        gate2_cfg["gate2"]["max_value_per_meeting"] = None
    return gate1_cfg, gate2_cfg


def _apply_gate_flags(scored: pd.DataFrame, paper_cfg: dict) -> pd.DataFrame:
    """Attach flag_none, gate1, gate2 (isolated lanes), production (live config) from ``flag_raw``."""
    gate1_cfg, gate2_cfg = _gate_configs(paper_cfg, gate2_caps=True)
    out = scored.copy()
    out["flag_none"] = pd.to_numeric(out["flag_raw"], errors="coerce").fillna(0).astype(int)

    g1in = out.copy()
    g1in["value_flag"] = g1in["flag_none"]
    g1in = g1in.drop(columns=["value_gate_reason"], errors="ignore")
    g1 = apply_value_gates(g1in, gate1_cfg)
    out["flag_gate1"] = pd.to_numeric(g1["value_flag"], errors="coerce").fillna(0).astype(int)
    out["gate1_reason"] = g1.get("value_gate_reason")

    g2in = out.copy()
    g2in["value_flag"] = g2in["flag_none"]
    g2in = g2in.drop(columns=["value_gate_reason"], errors="ignore")
    g2 = apply_value_gates(g2in, gate2_cfg)
    out["flag_gate2"] = pd.to_numeric(g2["value_flag"], errors="coerce").fillna(0).astype(int)
    out["gate2_reason"] = g2.get("value_gate_reason")

    pin = out.copy()
    pin["value_flag"] = pin["flag_none"]
    pin = pin.drop(columns=["value_gate_reason"], errors="ignore")
    prod = apply_value_gates(pin, paper_cfg)
    out["flag_production"] = pd.to_numeric(prod["value_flag"], errors="coerce").fillna(0).astype(int)
    out["production_reason"] = prod.get("value_gate_reason")
    return out


def _apply_gate2_only(scored: pd.DataFrame, paper_cfg: dict, *, gate2_caps: bool) -> pd.DataFrame:
    """Gate2 flags with optional cap disable (for sensitivity)."""
    _, gate2_cfg = _gate_configs(paper_cfg, gate2_caps=gate2_caps)
    out = scored.copy()
    out["flag_none"] = pd.to_numeric(out["flag_raw"], errors="coerce").fillna(0).astype(int)
    g2in = out.copy()
    g2in["value_flag"] = g2in["flag_none"]
    g2in = g2in.drop(columns=["value_gate_reason"], errors="ignore")
    g2 = apply_value_gates(g2in, gate2_cfg)
    out["flag_gate2"] = pd.to_numeric(g2["value_flag"], errors="coerce").fillna(0).astype(int)
    out["gate2_reason"] = g2.get("value_gate_reason")
    return out


def _settle(frame: pd.DataFrame, flag_col: str) -> dict[str, float | int | None]:
    picks = frame[frame[flag_col] == 1]
    if picks.empty:
        return {"picks": 0, "settled": 0, "hit_rate": None, "roi_pct": None, "pnl_units": 0.0}
    n = 0
    hits = 0
    pnl = 0.0
    for rec in picks.to_dict(orient="records"):
        p, status = _each_way_pnl(
            finish_pos=int(rec["finish_pos"]),
            bet_type="each_way",
            stake=1.0,
            win_decimal=float(rec["win_decimal"]),
            place_fraction=float(rec.get("place_fraction") or 0.25),
            places=int(rec.get("places") or 3),
        )
        pnl += float(p)
        n += 1
        if status in ("won", "placed"):
            hits += 1
    return {
        "picks": n,
        "settled": n,
        "hit_rate": (hits / n) if n else None,
        "roi_pct": (pnl / n * 100) if n else None,
        "pnl_units": pnl,
    }


def _delta(a: dict[str, float | int | None], b: dict[str, float | int | None]) -> dict[str, float | int | None]:
    def _f(v: object) -> float | None:
        if v is None:
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    ap, bp = _f(a.get("picks")), _f(b.get("picks"))
    ah, bh = _f(a.get("hit_rate")), _f(b.get("hit_rate"))
    ar, br = _f(a.get("roi_pct")), _f(b.get("roi_pct"))
    au, bu = _f(a.get("pnl_units")), _f(b.get("pnl_units"))
    return {
        "pick_change": int((ap or 0) - (bp or 0)),
        "hit_rate_change_pp": ((ah - bh) * 100.0) if ah is not None and bh is not None else None,
        "roi_change_pp": (ar - br) if ar is not None and br is not None else None,
        "pnl_change_units": (au - bu) if au is not None and bu is not None else None,
    }


def _empty_report(start: str, end: str, message: str) -> GateBenchmarkReport:
    z = {"picks": 0, "settled": 0, "hit_rate": None, "roi_pct": None, "pnl_units": 0.0}
    return GateBenchmarkReport(
        start=start,
        end=end,
        card_days=0,
        races=0,
        runners=0,
        none=z,
        gate1=z,
        gate2=z,
        production=z,
        delta_gate1_vs_none={},
        delta_gate2_vs_gate1={},
        delta_gate2_vs_none={},
        delta_production_vs_none={},
        delta_production_vs_gate2={},
        blocked_reasons_gate1={},
        blocked_reasons_gate2={},
        blocked_reasons_production={},
        message=message,
    )


def _score_day_rows(
    *,
    card_date: str,
    day: pd.DataFrame,
    db: Path,
    full_hist: pd.DataFrame,
    paper_cfg: dict,
    write_snapshots: bool,
    config_hash: str,
) -> list[dict]:
    day = merge_upcoming_enrich(db, day, str(card_date))
    odds = day[["runner_id", "win_decimal", "place_fraction", "places"]].copy()
    outcomes = day.set_index("runner_id")["finish_pos"].to_dict()
    min_place_ev = float(paper_cfg.get("min_place_ev", 0.05))
    min_combo = float(paper_cfg.get("min_combo_bayes_place", 0.22))

    scored = score_upcoming_cards(
        day.drop(columns=["finish_pos"], errors="ignore"),
        database=db,
        odds=odds,
        persist=False,
        hist_frame=full_hist,
        hist_before_date=str(card_date),
        write_snapshot=False,
    )
    scored["place_ev"] = pd.to_numeric(scored["place_ev"], errors="coerce")
    scored["combo_bayes_place"] = pd.to_numeric(scored["combo_bayes_place"], errors="coerce")
    scored["flag_raw"] = (
        (scored["place_ev"] >= min_place_ev) & (scored["combo_bayes_place"] >= min_combo)
    ).astype(int)

    if write_snapshots:
        snap = scored.copy()
        upsert_snapshots(
            db,
            str(card_date),
            snap,
            odds_source="sp",
            config_hash=config_hash,
            finish_by_runner={str(k): int(v) for k, v in outcomes.items()},
            paper_cfg=paper_cfg,
        )

    gated = _apply_gate_flags(scored, paper_cfg)
    rows: list[dict] = []
    for rec in gated.to_dict(orient="records"):
        finish = outcomes.get(rec["runner_id"])
        if finish is None:
            continue
        rec["finish_pos"] = int(finish)
        rec["card_date"] = str(card_date)
        rows.append(rec)
    return rows


def _build_benchmark_frame(
    *,
    db: Path,
    start: str,
    end: str,
    paper_cfg: dict,
    use_snapshots: bool,
    write_snapshots: bool,
    snapshot_config_hash: str | None = None,
) -> tuple[pd.DataFrame, str, str]:
    config_hash = resolve_snapshot_config_hash(
        db, paper_cfg, explicit=snapshot_config_hash
    )
    if use_snapshots:
        snap = load_snapshots(db, start, end, config_hash=config_hash)
        if not snap.empty:
            gated = _apply_gate_flags(snap, paper_cfg)
            gated = gated[gated["finish_pos"].notna()].copy()
            return gated, "snapshots", config_hash

    cards = _load_historical_cards(db, start, end)
    if cards.empty:
        return pd.DataFrame(), "scored", config_hash

    full_hist = load_runner_frame(db)
    rows: list[dict] = []
    for card_date in sorted(cards["card_date"].unique()):
        day = cards[cards["card_date"] == card_date].copy()
        day = day[day["win_decimal"].notna() & (day["win_decimal"] >= 1.01)]
        if day.empty:
            continue
        day = merge_upcoming_enrich(db, day, str(card_date))
        rows.extend(
            _score_day_rows(
                card_date=str(card_date),
                day=day,
                db=db,
                full_hist=full_hist,
                paper_cfg=paper_cfg,
                write_snapshots=write_snapshots,
                config_hash=config_hash,
            )
        )
    return pd.DataFrame(rows), "scored", config_hash


def backfill_scored_snapshots(
    *,
    start: str,
    end: str,
    database: Path | None = None,
    force: bool = False,
) -> dict:
    """Score historical card days and persist immutable snapshots (no gate re-score needed later)."""
    cfg = load_config()
    db = database or db_path(cfg)
    paper_cfg = cfg.get("paper", {})
    config_hash = scoring_config_hash(paper_cfg)

    def _coverage_payload() -> dict:
        cov = snapshot_coverage(db, start, end, config_hash=config_hash)
        from hibs_racing.features.runner_enrich_backfill import coverage_report

        enrich_cov = coverage_report(db, start=start, end=end)
        return {
            **cov,
            "coverage_kind": "snapshot_card_day_coverage",
            "snapshot_coverage_pct": cov.get("coverage_pct"),
            "enrich_coverage": enrich_cov,
        }

    if not force:
        cov = _coverage_payload()
        if cov["complete"]:
            return {
                "start": start,
                "end": end,
                "rows_written": 0,
                "message": "Snapshots already complete for range; use --force to rebuild.",
                **cov,
            }

    cards = _load_historical_cards(db, start, end)
    if cards.empty:
        return {"start": start, "end": end, "rows_written": 0, "message": "No historical cards."}

    full_hist = load_runner_frame(db)
    total = 0
    days = 0
    for card_date in sorted(cards["card_date"].unique()):
        day = cards[cards["card_date"] == card_date].copy()
        day = day[day["win_decimal"].notna() & (day["win_decimal"] >= 1.01)]
        if day.empty:
            continue
        day = merge_upcoming_enrich(db, day, str(card_date))
        odds = day[["runner_id", "win_decimal", "place_fraction", "places"]].copy()
        outcomes = day.set_index("runner_id")["finish_pos"].to_dict()
        min_place_ev = float(paper_cfg.get("min_place_ev", 0.05))
        min_combo = float(paper_cfg.get("min_combo_bayes_place", 0.22))

        scored = score_upcoming_cards(
            day.drop(columns=["finish_pos"], errors="ignore"),
            database=db,
            odds=odds,
            persist=False,
            hist_frame=full_hist,
            hist_before_date=str(card_date),
            write_snapshot=False,
        )
        scored["place_ev"] = pd.to_numeric(scored["place_ev"], errors="coerce")
        scored["combo_bayes_place"] = pd.to_numeric(scored["combo_bayes_place"], errors="coerce")
        scored["flag_raw"] = (
            (scored["place_ev"] >= min_place_ev) & (scored["combo_bayes_place"] >= min_combo)
        ).astype(int)
        total += upsert_snapshots(
            db,
            str(card_date),
            scored,
            odds_source="sp",
            config_hash=config_hash,
            finish_by_runner={str(k): int(v) for k, v in outcomes.items()},
            paper_cfg=paper_cfg,
        )
        days += 1

    cov = _coverage_payload()
    from hibs_racing.institutional.run_manifest import build_run_manifest, persist_run_manifest
    from hibs_racing.institutional.ledger_events import append_ledger_event

    manifest = build_run_manifest(
        run_kind="snapshot_backfill",
        card_date=None,
        runner_count=total,
        extras={"start": start, "end": end, "card_days_written": days, **cov},
    )
    mid = persist_run_manifest(manifest)
    append_ledger_event(event_type="manifest_written", manifest_id=mid, payload=manifest.to_dict())

    return {
        "start": start,
        "end": end,
        "card_days_written": days,
        "rows_written": total,
        "manifest_id": mid,
        "message": f"Wrote {total} snapshot rows across {days} card days.",
        **cov,
    }


def run_gate_benchmark(
    *,
    start: str | None = None,
    end: str | None = None,
    database: Path | None = None,
    use_snapshots: bool = True,
    write_snapshots: bool = False,
    include_slippage: bool = True,
    gate2_caps: bool = True,
    snapshot_config_hash: str | None = None,
) -> GateBenchmarkReport:
    cfg = load_config()
    db = database or db_path(cfg)
    paper_cfg = cfg.get("paper", {})
    max_start, max_end = _historical_bounds(db)
    start_s = start or max_start
    end_s = end or max_end
    if not start_s or not end_s:
        return _empty_report("", "", "No historical settled runners with SP available.")

    frame, source, snap_hash = _build_benchmark_frame(
        db=db,
        start=start_s,
        end=end_s,
        paper_cfg=paper_cfg,
        use_snapshots=use_snapshots,
        write_snapshots=write_snapshots,
        snapshot_config_hash=snapshot_config_hash,
    )

    if gate2_caps is False and not frame.empty:
        frame = _apply_gate2_only(
            frame.drop(columns=["flag_gate2", "gate2_reason"], errors="ignore"),
            paper_cfg,
            gate2_caps=False,
        )
        gate1_cfg, _ = _gate_configs(paper_cfg)
        g1in = frame.copy()
        g1in["value_flag"] = frame["flag_none"]
        g1in = g1in.drop(columns=["value_gate_reason"], errors="ignore")
        g1 = apply_value_gates(g1in, gate1_cfg)
        frame["flag_gate1"] = pd.to_numeric(g1["value_flag"], errors="coerce").fillna(0).astype(int)
        frame["gate1_reason"] = g1.get("value_gate_reason")

    if frame.empty:
        return _empty_report(start_s, end_s, f"No scored rows between {start_s} and {end_s}.")

    none_stats = _settle(frame, "flag_none")
    gate1_stats = _settle(frame, "flag_gate1")
    gate2_stats = _settle(frame, "flag_gate2")
    production_stats = _settle(frame, "flag_production")
    blocked1 = (
        frame.loc[frame["flag_none"].eq(1) & frame["flag_gate1"].eq(0), "gate1_reason"]
        .dropna()
        .astype(str)
        .value_counts()
        .to_dict()
    )
    blocked2 = (
        frame.loc[frame["flag_none"].eq(1) & frame["flag_gate2"].eq(0), "gate2_reason"]
        .dropna()
        .astype(str)
        .value_counts()
        .to_dict()
    )
    blocked_prod = (
        frame.loc[frame["flag_none"].eq(1) & frame["flag_production"].eq(0), "production_reason"]
        .dropna()
        .astype(str)
        .value_counts()
        .to_dict()
    )

    slip_report: dict[str, dict[str, float | int | None]] = {}
    if include_slippage:
        for bps in default_slip_bps_list(paper_cfg):
            stressed = apply_slippage_to_frame(
                frame.drop(columns=["flag_none", "flag_gate1", "flag_gate2", "gate1_reason", "gate2_reason"], errors="ignore"),
                bps,
                paper_cfg=paper_cfg,
            )
            stressed = _apply_gate_flags(stressed, paper_cfg)
            slip_report[f"{int(bps)}bps"] = {
                "none": _settle(stressed, "flag_none"),
                "gate1": _settle(stressed, "flag_gate1"),
                "gate2": _settle(stressed, "flag_gate2"),
                "production": _settle(stressed, "flag_production"),
            }

    msg = (
        f"Benchmark {start_s} → {end_s} [{source}]: none={int(none_stats['picks'])} picks, "
        f"gate1={int(gate1_stats['picks'])}, gate2={int(gate2_stats['picks'])}, "
        f"production={int(production_stats['picks'])}."
    )
    return GateBenchmarkReport(
        start=start_s,
        end=end_s,
        card_days=int(frame["card_date"].nunique()),
        races=int(frame["race_id"].nunique()),
        runners=int(len(frame)),
        none=none_stats,
        gate1=gate1_stats,
        gate2=gate2_stats,
        production=production_stats,
        delta_gate1_vs_none=_delta(gate1_stats, none_stats),
        delta_gate2_vs_gate1=_delta(gate2_stats, gate1_stats),
        delta_gate2_vs_none=_delta(gate2_stats, none_stats),
        delta_production_vs_none=_delta(production_stats, none_stats),
        delta_production_vs_gate2=_delta(production_stats, gate2_stats),
        blocked_reasons_gate1=blocked1,
        blocked_reasons_gate2=blocked2,
        blocked_reasons_production=blocked_prod,
        slippage=slip_report,
        snapshot_source=source,
        snapshot_config_hash=snap_hash,
        message=msg,
    )


def _month_periods(start: date, end: date) -> list[tuple[str, str, str]]:
    """Calendar months between start and end inclusive → (label, start_iso, end_iso)."""
    periods: list[tuple[str, str, str]] = []
    cur = date(start.year, start.month, 1)
    if cur < start:
        cur = start
    while cur <= end:
        if cur.month == 12:
            next_month = date(cur.year + 1, 1, 1)
        else:
            next_month = date(cur.year, cur.month + 1, 1)
        month_end = min(next_month - timedelta(days=1), end)
        month_start = max(cur, start)
        if month_start <= month_end:
            label = month_start.strftime("%Y-%m")
            periods.append((label, month_start.isoformat(), month_end.isoformat()))
        cur = next_month
    return periods


def _aggregate_mode(reports: list[GateBenchmarkReport], key: str) -> dict[str, float | int | None]:
    picks = sum(int(getattr(r, key)["picks"]) for r in reports)  # type: ignore[index]
    settled = sum(int(getattr(r, key)["settled"]) for r in reports)  # type: ignore[index]
    pnl = sum(float(getattr(r, key)["pnl_units"]) for r in reports)  # type: ignore[index]
    if not settled:
        return {"picks": 0, "settled": 0, "hit_rate": None, "roi_pct": None, "pnl_units": 0.0}
    hit_num = sum(
        float(getattr(r, key)["hit_rate"]) * int(getattr(r, key)["settled"])  # type: ignore[index]
        for r in reports
        if getattr(r, key)["hit_rate"] is not None
    )
    return {
        "picks": picks,
        "settled": settled,
        "hit_rate": hit_num / settled,
        "roi_pct": (pnl / settled) * 100,
        "pnl_units": pnl,
    }


@dataclass
class GateWalkforwardReport:
    start: str
    end: str
    periods: list[dict]
    aggregate: dict
    months_total: int
    months_with_data: int
    gate1_roi_wins_vs_none: int
    gate2_roi_wins_vs_gate1: int
    gate2_roi_wins_vs_none: int
    message: str

    def to_dict(self) -> dict:
        return {
            "start": self.start,
            "end": self.end,
            "months_total": self.months_total,
            "months_with_data": self.months_with_data,
            "gate1_roi_wins_vs_none": self.gate1_roi_wins_vs_none,
            "gate2_roi_wins_vs_gate1": self.gate2_roi_wins_vs_gate1,
            "gate2_roi_wins_vs_none": self.gate2_roi_wins_vs_none,
            "aggregate": self.aggregate,
            "periods": self.periods,
            "message": self.message,
        }


def run_gate_benchmark_walkforward(
    *,
    start: str | None = None,
    end: str | None = None,
    database: Path | None = None,
    progress_path: Path | None = None,
    use_snapshots: bool = True,
    write_snapshots: bool = False,
    snapshot_config_hash: str | None = None,
) -> GateWalkforwardReport:
    """Month-by-month OOS-style gate benchmark; aggregates pooled totals + per-period rows."""
    cfg = load_config()
    db = database or db_path(cfg)
    max_start, max_end = _historical_bounds(db)
    start_s = start or max_start
    end_s = end or max_end
    if not start_s or not end_s:
        return GateWalkforwardReport(
            start="",
            end="",
            periods=[],
            aggregate={},
            months_total=0,
            months_with_data=0,
            gate1_roi_wins_vs_none=0,
            gate2_roi_wins_vs_gate1=0,
            gate2_roi_wins_vs_none=0,
            message="No historical data.",
        )

    start_d = date.fromisoformat(start_s)
    end_d = date.fromisoformat(end_s)
    month_windows = _month_periods(start_d, end_d)
    period_rows: list[dict] = []
    reports: list[GateBenchmarkReport] = []
    g1_wins = g2_wins_g1 = g2_wins_none = 0

    for label, p_start, p_end in month_windows:
        rep = run_gate_benchmark(
            start=p_start,
            end=p_end,
            database=db,
            use_snapshots=use_snapshots,
            write_snapshots=write_snapshots,
            include_slippage=False,
            snapshot_config_hash=snapshot_config_hash,
        )
        row = {
            "period": label,
            "start": p_start,
            "end": p_end,
            "card_days": rep.card_days,
            "none": rep.none,
            "gate1": rep.gate1,
            "gate2": rep.gate2,
            "delta_gate1_vs_none": rep.delta_gate1_vs_none,
            "delta_gate2_vs_gate1": rep.delta_gate2_vs_gate1,
            "delta_gate2_vs_none": rep.delta_gate2_vs_none,
            "snapshot_source": rep.snapshot_source,
        }
        period_rows.append(row)
        if progress_path is not None:
            progress_path.parent.mkdir(parents=True, exist_ok=True)
            partial = {
                "start": start_s,
                "end": end_s,
                "completed_periods": period_rows,
                "last_period": label,
            }
            progress_path.write_text(json.dumps(partial, indent=2), encoding="utf-8")
        if rep.runners > 0:
            reports.append(rep)
            n_roi = rep.none.get("roi_pct")
            g1_roi = rep.gate1.get("roi_pct")
            g2_roi = rep.gate2.get("roi_pct")
            if n_roi is not None and g1_roi is not None and g1_roi > n_roi:
                g1_wins += 1
            if g1_roi is not None and g2_roi is not None and g2_roi > g1_roi:
                g2_wins_g1 += 1
            if n_roi is not None and g2_roi is not None and g2_roi > n_roi:
                g2_wins_none += 1

    if not reports:
        return GateWalkforwardReport(
            start=start_s,
            end=end_s,
            periods=period_rows,
            aggregate={},
            months_total=len(month_windows),
            months_with_data=0,
            gate1_roi_wins_vs_none=0,
            gate2_roi_wins_vs_gate1=0,
            gate2_roi_wins_vs_none=0,
            message=f"No scored data between {start_s} and {end_s}.",
        )

    none_a = _aggregate_mode(reports, "none")
    g1_a = _aggregate_mode(reports, "gate1")
    g2_a = _aggregate_mode(reports, "gate2")
    aggregate = {
        "none": none_a,
        "gate1": g1_a,
        "gate2": g2_a,
        "delta_gate1_vs_none": _delta(g1_a, none_a),
        "delta_gate2_vs_gate1": _delta(g2_a, g1_a),
        "delta_gate2_vs_none": _delta(g2_a, none_a),
    }
    msg = (
        f"Walk-forward {start_s} → {end_s}: {len(reports)}/{len(month_windows)} months with data. "
        f"Gate1 ROI beat none in {g1_wins} months; gate2 beat gate1 in {g2_wins_g1} months."
    )
    return GateWalkforwardReport(
        start=start_s,
        end=end_s,
        periods=period_rows,
        aggregate=aggregate,
        months_total=len(month_windows),
        months_with_data=len(reports),
        gate1_roi_wins_vs_none=g1_wins,
        gate2_roi_wins_vs_gate1=g2_wins_g1,
        gate2_roi_wins_vs_none=g2_wins_none,
        message=msg,
    )
