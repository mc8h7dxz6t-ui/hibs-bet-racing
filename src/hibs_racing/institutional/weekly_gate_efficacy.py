"""Append-only weekly gate efficacy + execution slippage report."""

from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from hibs_racing.backtest.gate_benchmark import _apply_gate_flags, _settle
from hibs_racing.backtest.snapshot_store import load_snapshots, scoring_config_hash
from hibs_racing.config import ROOT, db_path, load_config
from hibs_racing.features.store import connect, init_db
from hibs_racing.odds.exchange_quotes import slippage_bps
from hibs_racing.place.paper_ledger import _each_way_pnl


REPORT_PATH = ROOT / "reports" / "weekly_gate_efficacy.md"


def _week_bounds(week_ended: date) -> tuple[str, str]:
    end = week_ended.isoformat()
    start = (week_ended - timedelta(days=6)).isoformat()
    return start, end


def _attach_sp(frame: pd.DataFrame, db: Path) -> pd.DataFrame:
    if frame.empty:
        return frame
    out = frame.copy()
    if "sp_decimal" in out.columns and out["sp_decimal"].notna().any():
        return out
    with connect(db) as conn:
        sp_map: dict[str, float] = {}
        for rid in out["runner_id"].astype(str).unique():
            card_date = out.loc[out["runner_id"].astype(str) == rid, "card_date"].iloc[0]
            row = conn.execute(
                """
                SELECT sp_decimal FROM runners
                WHERE runner_id = ? AND race_date = ? AND sp_decimal IS NOT NULL
                LIMIT 1
                """,
                (str(rid), str(card_date)),
            ).fetchone()
            if row and row[0] is not None:
                sp_map[str(rid)] = float(row[0])
        out["sp_decimal"] = out["runner_id"].astype(str).map(sp_map)
    return out


def _baseline_back_map(db: Path, runner_ids: set[str], card_dates: set[str]) -> dict[str, float]:
    if not runner_ids:
        return {}
    out: dict[str, float] = {}
    with connect(db) as conn:
        for cid in card_dates:
            rows = conn.execute(
                """
                SELECT runner_id, back_price FROM exchange_quotes
                WHERE card_date = ? AND poll_milestone = 'baseline' AND back_price IS NOT NULL
                ORDER BY timestamp ASC
                """,
                (str(cid),),
            ).fetchall()
            for rid, bp in rows:
                key = f"{rid}|{cid}"
                if key not in out and bp is not None:
                    out[key] = float(bp)
    return out


def _settle_lane(
    frame: pd.DataFrame,
    flag_col: str,
    *,
    price_col: str = "win_decimal",
) -> dict[str, float | int | None]:
    picks = frame[frame[flag_col] == 1].copy()
    if picks.empty:
        return {"picks": 0, "settled": 0, "hit_rate": None, "roi_pct": None, "pnl_units": 0.0, "avg_slippage_bps": None}
    n = 0
    hits = 0
    pnl = 0.0
    slips: list[float] = []
    for rec in picks.to_dict(orient="records"):
        price = rec.get(price_col)
        if price is None or (isinstance(price, float) and pd.isna(price)):
            continue
        p, status = _each_way_pnl(
            finish_pos=int(rec["finish_pos"]),
            bet_type="each_way",
            stake=1.0,
            win_decimal=float(price),
            place_fraction=float(rec.get("place_fraction") or 0.25),
            places=int(rec.get("places") or 3),
        )
        pnl += float(p)
        n += 1
        if status in ("won", "placed"):
            hits += 1
        sp = rec.get("sp_decimal")
        slip = slippage_bps(rec.get("executed_back") or rec.get("win_decimal"), sp)
        if slip is not None:
            slips.append(slip)
    return {
        "picks": n,
        "settled": n,
        "hit_rate": (hits / n) if n else None,
        "roi_pct": (pnl / n * 100) if n else None,
        "pnl_units": pnl,
        "avg_slippage_bps": (sum(slips) / len(slips)) if slips else None,
    }


def build_weekly_report(
    *,
    week_ended: date | None = None,
    database: Path | None = None,
) -> dict:
    week_ended = week_ended or date.today()
    start, end = _week_bounds(week_ended)
    cfg = load_config()
    db = database or db_path(cfg)
    paper = cfg.get("paper", {})
    snap = load_snapshots(db, start, end, config_hash=scoring_config_hash(paper))
    if snap.empty:
        return {"ok": False, "error": "no snapshots", "start": start, "end": end}

    snap = snap[snap["finish_pos"].notna()].copy()
    snap = _attach_sp(snap, db)
    gated = _apply_gate_flags(snap, paper)

    baselines = _baseline_back_map(
        db,
        set(gated["runner_id"].astype(str)),
        set(gated["card_date"].astype(str)),
    )
    gated["executed_back"] = gated.apply(
        lambda r: baselines.get(f"{r['runner_id']}|{r['card_date']}"),
        axis=1,
    )

    lanes = {
        "Raw Value (No Gates)": "flag_none",
        "Gate1 Only": "flag_gate1",
        "Production Lane": "flag_production",
    }
    tweak_cfg = deepcopy(paper)
    tweak_cfg.setdefault("gate2", {})
    if isinstance(tweak_cfg["gate2"], dict):
        tweak_cfg["gate2"]["enabled"] = True
        tweak_cfg["gate2"]["max_value_per_meeting"] = 8
        tweak_cfg["gate2"]["max_value_per_race"] = 3
        tweak_cfg["gate2"]["min_confidence"] = 0.50
    tweak_gated = _apply_gate_flags(snap, tweak_cfg)
    gated = gated.copy()
    gated["flag_tweak_looser"] = tweak_gated["flag_production"]
    lanes["Tweak (Looser Gate2)"] = "flag_tweak_looser"

    table: dict[str, dict] = {}
    for label, col in lanes.items():
        sp_stats = _settle_lane(gated, col, price_col="sp_decimal")
        ex_stats = _settle_lane(
            gated,
            col,
            price_col="executed_back",
        )
        if ex_stats["settled"] == 0:
            ex_stats = _settle_lane(gated, col, price_col="win_decimal")
        table[label] = {
            "sp": sp_stats,
            "executed": ex_stats,
        }

    return {
        "ok": True,
        "week_ended": week_ended.isoformat(),
        "start": start,
        "end": end,
        "runners": len(snap),
        "card_days": int(snap["card_date"].nunique()),
        "config_hash": scoring_config_hash(paper),
        "lanes": table,
    }


def format_weekly_markdown(payload: dict) -> str:
    if not payload.get("ok"):
        return f"# Weekly Gate Efficacy — error\n\n{payload.get('error', 'unknown')}\n"

    ended = payload["week_ended"]
    lines = [
        f"## Weekly Institutional Gate Efficacy Report (Ended {ended})",
        "",
        f"_Window: {payload['start']} → {payload['end']} · "
        f"{payload['card_days']} card days · {payload['runners']} settled runners · "
        f"config `{payload['config_hash']}`_",
        "",
        "| Lane | Settled Picks | Hit Rate % | SP ROI % | Executed ROI % | Avg Slippage (BPS) |",
        "| :--- | :--- | :--- | :--- | :--- | :--- |",
    ]

    for label, stats in payload["lanes"].items():
        sp = stats["sp"]
        ex = stats["executed"]
        hit = sp.get("hit_rate")
        hit_s = f"{hit * 100:.1f}" if hit is not None else "—"
        sp_roi = sp.get("roi_pct")
        ex_roi = ex.get("roi_pct")
        slip = ex.get("avg_slippage_bps")
        lines.append(
            f"| {label} | {sp.get('settled', 0)} | {hit_s} | "
            f"{sp_roi if sp_roi is not None else '—'} | "
            f"{ex_roi if ex_roi is not None else '—'} | "
            f"{slip if slip is not None else '—'} |"
        )

    prod = payload["lanes"].get("Production Lane", {}).get("sp", {})
    raw = payload["lanes"].get("Raw Value (No Gates)", {}).get("sp", {})
    prod_roi = prod.get("roi_pct")
    raw_roi = raw.get("roi_pct")
    if prod_roi is not None and raw_roi is not None:
        lines.extend(
            [
                "",
                f"**Production − Raw SP ROI:** {prod_roi - raw_roi:+.1f} pp",
            ]
        )
    lines.append("")
    lines.append(f"_Generated {datetime.now(timezone.utc).replace(microsecond=0).isoformat()} UTC_")
    lines.append("")
    return "\n".join(lines)


def append_weekly_report(
    *,
    week_ended: date | None = None,
    report_path: Path | None = None,
    database: Path | None = None,
) -> dict:
    payload = build_weekly_report(week_ended=week_ended, database=database)
    path = report_path or REPORT_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    md = format_weekly_markdown(payload)
    header = f"# Weekly Institutional Gate Efficacy Ledger\n\n"
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        if not existing.startswith("# Weekly"):
            existing = header + existing
        body = existing.rstrip() + "\n\n---\n\n" + md
    else:
        body = header + md
    path.write_text(body, encoding="utf-8")
    payload["report_path"] = str(path)
    return payload
