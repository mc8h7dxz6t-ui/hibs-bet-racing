from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from hibs_racing.config import ROOT, db_path, load_config
from hibs_racing.place.paper_ledger import export_ledger_csv, ledger_stats, load_ledger_rows


def public_tracker_enabled() -> bool:
    return os.environ.get("HIBS_PUBLIC_TRACKER", "1").strip().lower() in {"1", "true", "yes", "on"}


def default_history_days() -> int:
    raw = os.environ.get("HIBS_TRACKER_HISTORY_DAYS", "60")
    try:
        return max(30, min(90, int(raw)))
    except ValueError:
        return 60


def daily_refresh_status() -> dict[str, Any]:
    """Last successful daily_refresh.sh run from automation logs."""
    log_path = ROOT / "logs" / "daily-settle-paper.log"
    if not log_path.exists():
        return {"scheduled": True, "last_ok": None, "message": "Awaiting first daily_refresh cron run"}
    text = log_path.read_text(encoding="utf-8", errors="replace")
    last_ok = None
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.strip() == "OK: daily-settle-paper" and i > 0:
            prev = lines[i - 1].strip()
            if prev.startswith("==="):
                last_ok = prev.strip("= ").split(" ", 1)[0]
            break
    mtime = datetime.fromtimestamp(log_path.stat().st_mtime, tz=timezone.utc).replace(microsecond=0).isoformat()
    return {
        "scheduled": True,
        "log_path": str(log_path),
        "last_modified_utc": mtime,
        "last_ok_utc": last_ok,
        "message": f"Paper picks logged on card refresh; auto-settled by daily_refresh.sh (log updated {mtime[:19]} UTC)",
    }


def _pnl_curve(rows: list[dict]) -> list[dict[str, Any]]:
    settled = [
        r
        for r in rows
        if r.get("status") != "open" and r.get("settled_at") and r.get("result_pnl") is not None
    ]
    settled.sort(key=lambda r: str(r.get("settled_at") or ""))
    cum = 0.0
    curve: list[dict[str, Any]] = []
    for row in settled:
        pnl = float(row["result_pnl"])
        cum += pnl
        day = str(row.get("settled_at") or row.get("card_date") or "")[:10]
        curve.append({"date": day, "daily_pnl": round(pnl, 2), "cum_pnl": round(cum, 2), "bet_id": row.get("bet_id")})
    return curve


def _clv_metrics(rows: list[dict]) -> dict[str, Any]:
    with_clv = [r for r in rows if r.get("closing_sp") and r.get("offered_win")]
    beats = [r for r in with_clv if int(r.get("clv_beat") or 0) == 1]
    n = len(with_clv)
    return {
        "n_with_closing_sp": n,
        "clv_beat_count": len(beats),
        "clv_beat_rate_pct": round(100.0 * len(beats) / n, 1) if n else None,
    }


def build_public_tracker_dict(
    *,
    history_days: int | None = None,
    limit: int = 500,
    database: Path | None = None,
    backtest: bool | None = False,
) -> dict[str, Any]:
    """Read-only trust-layer payload for /tracker and /api/tracker."""
    days = history_days if history_days is not None else default_history_days()
    days = max(7, min(90, int(days)))
    limit = max(10, min(2000, int(limit)))
    db = database or db_path(load_config())

    rows = load_ledger_rows(db, limit=limit, days=days, backtest=backtest)
    stats = ledger_stats(db, days=days, backtest=backtest).to_dict()
    value_settled = [r for r in rows if r.get("is_value_pick") and r.get("status") != "open"]
    clv = _clv_metrics(rows)
    curve = _pnl_curve(rows)

    return {
        "ok": True,
        "public": True,
        "read_only": True,
        "enabled": public_tracker_enabled(),
        "product": "hibs-racing",
        "ledger_kind": "backtest" if backtest else "forward",
        "history_days": days,
        "ledger_count": len(rows),
        "settled_count": stats.get("settled_bets", 0),
        "open_count": stats.get("open_bets", 0),
        "value_pick_count": stats.get("value_pick_count", 0),
        "stats": stats,
        "clv": clv,
        "pnl_curve": curve,
        "methodology": {
            "lock_rule": (
                "Each value-flagged each-way pick is logged to paper_bets at score time during "
                "daily_refresh.sh (--paper). One bet per runner/race — duplicates rejected."
            ),
            "settlement_rule": (
                "Results auto-joined from ingested raceform via race natural key (date+course+time), "
                "then horse/course fallbacks. Closing SP stored at settlement for CLV audit."
            ),
            "verification": (
                "Each row includes bet_id and SHA-256 verification_hash (bet_id|created_at|runner|odds|stake). "
                "Export CSV for third-party verification."
            ),
        },
        "daily_refresh": daily_refresh_status(),
        "ledger_rows": rows,
        "export_urls": {
            "csv": f"/api/tracker/export.csv?days={days}",
            "json": f"/api/tracker?days={days}",
        },
        "third_party_note": (
            "Paper ledger only — no live money. Submit CSV exports to independent verifiers "
            "(e.g. Smart Betting Club) to validate the track record."
        ),
    }
