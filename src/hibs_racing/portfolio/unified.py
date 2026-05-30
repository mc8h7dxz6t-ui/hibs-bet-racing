from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

from hibs_racing.config import load_config
from hibs_racing.place.public_tracker import build_public_tracker_dict


def _football_tracker_url() -> str:
    base = os.environ.get("HIBS_BET_BASE_URL", "http://127.0.0.1:5001").rstrip("/")
    days = int(os.environ.get("HIBS_PORTFOLIO_FOOTBALL_DAYS", "90"))
    override = os.environ.get("HIBS_BET_TRACKER_URL", "").strip()
    if override:
        return override
    return f"{base}/api/tracker?days={days}"


def _football_db_path() -> Path | None:
    raw = os.environ.get("HIBS_BET_DB_PATH", "").strip()
    if raw:
        path = Path(raw).expanduser()
        return path if path.exists() else None
    default = Path(os.environ.get("HIBS_BET_DATA_DIR", Path.home() / "Applications" / "data")).expanduser()
    candidate = default / "prediction_audit.sqlite"
    return candidate if candidate.exists() else None


def _fetch_football_via_api() -> dict[str, Any] | None:
    url = _football_tracker_url()
    try:
        with urlopen(url, timeout=8) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None


def _football_pnl_units(row: dict) -> float | None:
    """Flat 1u on value picks; model-only rows excluded from P&L."""
    if not row.get("has_value"):
        return None
    result = row.get("value_result")
    if result not in ("W", "L"):
        return None
    try:
        odds = float(row.get("value_odds") or 0)
    except (TypeError, ValueError):
        odds = 0.0
    if result == "W" and odds > 1:
        return odds - 1.0
    return -1.0


def _normalize_football_row(row: dict) -> dict[str, Any]:
    pnl = _football_pnl_units(row)
    return {
        "source": "hibs-bet",
        "sport": "football",
        "id": str(row.get("snapshot_id") or row.get("fixture_id")),
        "event_at": row.get("kickoff_utc"),
        "settled_at": row.get("result_recorded_at") if row.get("settled") else None,
        "description": row.get("match"),
        "league_or_meeting": row.get("league_code"),
        "selection": row.get("value_market") or row.get("model_pick"),
        "odds": row.get("value_odds"),
        "stake": 1.0 if row.get("has_value") else None,
        "result": row.get("value_result") if row.get("has_value") else row.get("model_result"),
        "pnl": pnl,
        "edge_pct": row.get("value_edge_pct"),
        "clv_pp": row.get("clv_pp"),
        "cohort": row.get("cohort"),
        "meta": {
            "fixture_id": row.get("fixture_id"),
            "verification_hash": row.get("verification_hash"),
            "model_pick": row.get("model_pick"),
            "locked_pre_kickoff": row.get("locked_pre_kickoff"),
        },
    }


def _load_football_from_sqlite(db_path: Path, *, days: int = 90) -> list[dict]:
    """Fallback when hibs-bet API is offline — read prediction_audit directly."""
    if not db_path.exists():
        return []
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT id, fixture_id, captured_at, kickoff_iso, league_code,
                   home_name, away_name, prediction_json, result_outcome,
                   result_status, result_recorded_at, enrich_summary_json
            FROM prediction_snapshots
            ORDER BY kickoff_iso DESC
            LIMIT 500
            """
        ).fetchall()
    finally:
        conn.close()

    out: list[dict] = []
    for r in rows:
        try:
            pred = json.loads(r["prediction_json"] or "{}")
        except json.JSONDecodeError:
            pred = {}
        value = None
        for key in ("value_bets", "value_bets_alt"):
            vb = pred.get(key) or {}
            if isinstance(vb, dict) and vb:
                value = max(vb.values(), key=lambda x: float((x or {}).get("roi_percent") or 0))
                break
        row = {
            "snapshot_id": r["id"],
            "fixture_id": r["fixture_id"],
            "kickoff_utc": r["kickoff_iso"],
            "league_code": r["league_code"],
            "match": f"{r['home_name']} v {r['away_name']}",
            "has_value": bool(value),
            "value_market": (value or {}).get("market_label"),
            "value_odds": (value or {}).get("odds"),
            "value_edge_pct": (value or {}).get("edge_pct"),
            "value_result": None,
            "model_pick": pred.get("predicted_outcome"),
            "model_result": None,
            "settled": bool(r["result_recorded_at"]),
            "result_recorded_at": r["result_recorded_at"],
            "cohort": "scale",
        }
        if r["result_outcome"] and value:
            pick = (value.get("outcome") or value.get("selection") or "").lower()
            row["value_result"] = "W" if pick == str(r["result_outcome"]).lower() else "L"
        out.append(_normalize_football_row(row))
    return out


def _normalize_racing_row(row: dict) -> dict[str, Any]:
    status = row.get("status") or "open"
    pnl = float(row["result_pnl"]) if row.get("result_pnl") is not None and status != "open" else None
    result = "pending"
    if status in ("won", "placed"):
        result = "W"
    elif status == "lost":
        result = "L"
    elif status == "open":
        result = "pending"
    event_at = f"{row.get('card_date') or ''}T{row.get('off_time') or '00:00'}:00"
    return {
        "source": "hibs-racing",
        "sport": "racing",
        "id": row.get("bet_id"),
        "event_at": event_at,
        "settled_at": row.get("settled_at"),
        "description": f"{row.get('horse_name')} @ {row.get('course')}",
        "league_or_meeting": row.get("course"),
        "selection": row.get("bet_type"),
        "odds": row.get("offered_win"),
        "stake": row.get("stake_units"),
        "result": result,
        "pnl": pnl,
        "edge_pct": (float(row["model_ev"]) * 100 if row.get("model_ev") is not None else None),
        "clv_pp": None,
        "cohort": "paper",
        "meta": {
            "race_id": row.get("race_id"),
            "runner_id": row.get("runner_id"),
            "is_value_pick": bool(row.get("is_value_pick")),
            "finish_pos": row.get("finish_pos"),
        },
    }


def build_unified_portfolio(*, football_days: int = 90, racing_limit: int = 200) -> dict[str, Any]:
    """Merge hibs-bet football tracker + hibs-racing paper ledger into one view."""
    football_source = "none"
    football_rows: list[dict] = []
    football_stats: dict[str, Any] = {}

    api_payload = _fetch_football_via_api()
    if api_payload and api_payload.get("ledger"):
        football_source = "api"
        football_rows = [_normalize_football_row(r) for r in api_payload["ledger"]]
        football_stats = {
            "settled_count": api_payload.get("settled_count"),
            "value_hit_rate_pct": api_payload.get("value_hit_rate_pct"),
            "ledger_count": api_payload.get("ledger_count"),
        }
    else:
        db = _football_db_path()
        if db:
            football_source = f"sqlite:{db}"
            football_rows = _load_football_from_sqlite(db, days=football_days)

    racing_tracker = build_public_tracker_dict(limit=racing_limit)
    racing_rows = [_normalize_racing_row(r) for r in racing_tracker.get("ledger_rows") or []]
    racing_stats = racing_tracker.get("stats") or {}

    combined = football_rows + racing_rows
    combined.sort(key=lambda r: str(r.get("event_at") or ""), reverse=True)

    fb_pnl = sum(r["pnl"] for r in football_rows if r.get("pnl") is not None)
    rc_pnl = sum(r["pnl"] for r in racing_rows if r.get("pnl") is not None)
    fb_settled = sum(1 for r in football_rows if r.get("pnl") is not None)
    rc_settled = sum(1 for r in racing_rows if r.get("pnl") is not None)

    return {
        "ok": True,
        "updated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "football_source": football_source,
        "football_stats": football_stats,
        "racing_stats": racing_stats,
        "summary": {
            "total_rows": len(combined),
            "football_rows": len(football_rows),
            "racing_rows": len(racing_rows),
            "football_pnl_units": round(fb_pnl, 2),
            "racing_pnl_units": round(rc_pnl, 2),
            "combined_pnl_units": round(fb_pnl + rc_pnl, 2),
            "football_settled": fb_settled,
            "racing_settled": rc_settled,
        },
        "ledger": combined,
        "links": {
            "football_tracker": os.environ.get("HIBS_BET_BASE_URL", "http://127.0.0.1:5001") + "/tracker",
            "racing_tracker": "/tracker",
        },
    }
