"""Inst++ data producer SLO for hibs-racing — cards, odds, scrape cycle."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


def _utc_today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def card_store_status() -> Dict[str, Any]:
    try:
        from hibs_racing.cards.query import load_scored_cards
        from hibs_racing.scrapers.racing_scrape_api import odds_coverage_summary

        frame = load_scored_cards()
        cov = odds_coverage_summary(frame)
        dates = []
        if not frame.empty and "card_date" in frame.columns:
            dates = sorted(frame["card_date"].astype(str).unique().tolist())
        today = _utc_today()
        latest = dates[-1] if dates else None
        card_fresh = bool(latest and str(latest) >= today)
        return {
            "ok": len(frame) > 0 and card_fresh,
            "runner_count": len(frame),
            "race_count": int(frame["race_id"].nunique()) if not frame.empty and "race_id" in frame.columns else 0,
            "latest_card_date": latest,
            "card_fresh": card_fresh,
            "today_utc": today,
            "odds_coverage_pct": cov.get("coverage_pct"),
            "priced_runners": cov.get("priced"),
            "message": "ok" if len(frame) > 0 else "empty_store",
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:120], "message": "store_error"}


def robust_scrape_status() -> Dict[str, Any]:
    try:
        from hibs_racing.scrapers.robust_scrape_cycle import robust_scrape_slo_status

        return robust_scrape_slo_status()
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:120]}


def build_data_producer_snapshot() -> Dict[str, Any]:
    cards = card_store_status()
    scrape = robust_scrape_status()
    try:
        from hibs_racing.scrapers.scrape_resilience import scrape_resilience_status

        resilience = scrape_resilience_status()
    except Exception:
        resilience = {"ok": True}
    try:
        from hibs_racing.racing_api_guard import status_payload as api_guard_status

        api_guard = api_guard_status()
    except Exception:
        api_guard = {}
    try:
        from hibs_racing.matchbook_guard import status_payload as mb_guard_status

        mb_guard = mb_guard_status()
    except Exception:
        mb_guard = {}
    producers = {
        "racing_cards": cards,
        "robust_scrape": scrape,
        "resilience": resilience,
        "racing_api_guard": api_guard,
        "matchbook_guard": mb_guard,
    }
    ok = bool(cards.get("ok")) and scrape.get("ok") is not False
    return {
        "layer": "racing_data_producer_slo",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "ok": ok,
        "producers": producers,
    }


def needs_data_producer_repair(snapshot: Optional[Dict[str, Any]] = None) -> bool:
    snap = snapshot or build_data_producer_snapshot()
    return not bool(snap.get("ok"))
