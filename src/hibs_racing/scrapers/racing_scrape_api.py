"""Scrape-first HTTP API layer for racing — mirrors hibs-bet low_source_api."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pandas as pd

from hibs_racing.cards.data_quality import runner_data_quality_pct
from hibs_racing.cards.dq_persist import merge_runners_preserve_best
from hibs_racing.cards.query import load_scored_cards
from hibs_racing.scrapers.multi_scraper_api import FIELD_LADDERS, catalog_summary


def resolve_cards_source(source: Optional[str] = None) -> str:
    from hibs_racing.racing_api_guard import racing_api_traffic_allowed
    from hibs_racing.scrape_first import default_cards_source, scrape_first_mode

    raw = (source or os.getenv("HIBS_RACING_SCRAPE_SOURCE") or "auto").strip().lower()
    if raw in ("auto", "racing_api", ""):
        if scrape_first_mode() or not racing_api_traffic_allowed():
            return default_cards_source() if scrape_first_mode() else "rpscrape"
        return "racing_api"
    return raw


def scrape_status_payload() -> Dict[str, Any]:
    from hibs_racing.racing_api_guard import status_payload as guard_status
    from hibs_racing.scrape_first import scrape_first_status
    from hibs_racing.scrapers.scrape_resilience import scrape_resilience_status

    cat = catalog_summary()
    return {
        "ok": True,
        "product": "hibs-racing",
        "mode": "scrape_first" if scrape_first_status().get("scrape_first") else "api_first",
        "scrape_first": scrape_first_status(),
        "field_ladders": cat.get("field_ladders") or FIELD_LADDERS,
        "targeted_overflow": cat.get("targeted_overflow") or [],
        "cards_source": resolve_cards_source(),
        "racing_api_guard": guard_status(),
        "api_pools": __import__("hibs_racing.api_pools", fromlist=["all_pool_status"]).all_pool_status(),
        "resilience": scrape_resilience_status(),
    }


def list_cards_payload(*, slim: bool = True, rescue: bool = False) -> Dict[str, Any]:
    frame = load_scored_cards()
    if frame.empty:
        return {
            "ok": True,
            "mode": "scrape_cards",
            "count": 0,
            "runners": [],
            "thin_data_count": 0,
        }
    rows: List[Dict[str, Any]] = []
    thin = 0
    for _, row in frame.iterrows():
        d = {k: row.get(k) for k in row.index}
        dq = runner_data_quality_pct(d)
        if dq < 70:
            thin += 1
        if slim:
            rows.append(
                {
                    "runner_id": d.get("runner_id"),
                    "horse_name": d.get("horse_name"),
                    "course": d.get("course"),
                    "off_time": d.get("off_time"),
                    "card_date": d.get("card_date"),
                    "win_decimal": d.get("win_decimal"),
                    "data_quality_pct": dq,
                }
            )
        else:
            if rescue:
                from hibs_racing.cards.runner_field_api import resolve_runner_fields

                rid = str(d.get("runner_id") or "")
                payload = resolve_runner_fields(rid, rescue=True) if rid else None
                if payload:
                    rows.append(payload)
                    continue
            d["data_quality_pct"] = dq
            rows.append(d)
    return {
        "ok": True,
        "mode": "scrape_cards_enriched" if rescue else "scrape_cards",
        "count": len(rows),
        "thin_data_count": thin,
        "runners": rows,
        "field_ladders": FIELD_LADDERS,
    }


def odds_coverage_summary(frame: Optional[pd.DataFrame] = None) -> Dict[str, Any]:
    df = frame if frame is not None else load_scored_cards()
    total = len(df)
    if total == 0:
        return {"total": 0, "priced": 0, "coverage_pct": 0.0, "ok": False}
    priced = 0
    if "win_decimal" in df.columns:
        priced = int((df["win_decimal"].notna() & (df["win_decimal"].astype(float) > 1.0)).sum())
    pct = round(100.0 * priced / total, 1)
    min_pct = float(os.getenv("HIBS_RACING_ODDS_COVERAGE_MIN_PCT", "40"))
    return {
        "total": total,
        "priced": priced,
        "coverage_pct": pct,
        "min_pct": min_pct,
        "ok": pct >= min_pct,
    }


def run_thin_rescue_pass(*, max_per_cycle: Optional[int] = None) -> Dict[str, Any]:
    from hibs_racing.data_quality_targets import racing_rescue_max_per_cycle

    cap = max_per_cycle
    if cap is None:
        cap = racing_rescue_max_per_cycle()
    frame = load_scored_cards()
    if frame.empty:
        return {"rescued": 0, "attempted": 0, "coverage": odds_coverage_summary(frame)}
    rescued = 0
    attempted = 0
    persisted = 0
    from hibs_racing.cards.runner_field_api import resolve_runner_fields
    from hibs_racing.data_quality_targets import racing_data_quality_target_pct, racing_thin_rescue_dq_pct

    thin_floor = racing_thin_rescue_dq_pct()
    target = racing_data_quality_target_pct()
    updates: List[Dict[str, Any]] = []
    from hibs_racing.scrapers.field_resolver import clear_race_enrich_cache

    clear_race_enrich_cache()
    for _, row in frame.iterrows():
        if cap <= 0:
            break
        d = {k: row.get(k) for k in row.index}
        dq_before = runner_data_quality_pct(d)
        if dq_before >= target and d.get("win_decimal"):
            continue
        if dq_before >= thin_floor and d.get("win_decimal"):
            continue
        cap -= 1
        attempted += 1
        rid = str(d.get("runner_id") or "")
        if not rid:
            continue
        payload = resolve_runner_fields(rid, rescue=True)
        if not payload:
            continue
        fields = payload.get("fields") or {}
        merged = dict(d)
        for key, val in fields.items():
            if val is not None:
                merged[key] = val
        dq_after = runner_data_quality_pct(merged)
        if dq_after > dq_before or (payload.get("rescued") and dq_after >= dq_before):
            rescued += 1
            updates.append(merged)
    if updates:
        from hibs_racing.cards.store import load_upcoming_runners, store_upcoming_runners

        existing = load_upcoming_runners()
        if existing.empty:
            existing = frame
        patch = pd.DataFrame(updates)
        merged = merge_runners_preserve_best(existing, patch)
        persisted = store_upcoming_runners(merged, source="thin_rescue")
    return {
        "rescued": rescued,
        "attempted": attempted,
        "persisted": persisted,
        "coverage": odds_coverage_summary(),
    }


def run_data_quality_reboost(
    *,
    target_pct: Optional[float] = None,
    max_rescue_passes: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Multi-stage DQ lift: enrich recovery → scrape thin rescue (repeat) toward 95%+.

    Uses scrape APIs (``resolve_runner_fields``) and offline enrich backfill.
    """
    from hibs_racing.cards.dq_persist import mean_runner_dq
    from hibs_racing.data_quality_targets import (
        racing_data_quality_target_pct,
        racing_enrich_recovery_min_pct,
    )

    target = target_pct if target_pct is not None else racing_data_quality_target_pct()
    passes = max_rescue_passes
    if passes is None:
        try:
            passes = max(1, int(os.getenv("HIBS_RACING_DQ_REBOOST_PASSES", "2")))
        except ValueError:
            passes = 2

    frame = load_scored_cards()
    mean_before = mean_runner_dq(frame)
    report: Dict[str, Any] = {
        "target_pct": target,
        "mean_dq_before": mean_before,
        "runner_count": len(frame),
        "ok": mean_before >= target,
    }

    if mean_before >= target:
        report["mean_dq_after"] = mean_before
        report["skipped"] = True
        return report

    try:
        from hibs_racing.cards.upcoming_dq_recovery import run_upcoming_dq_recovery

        report["upcoming_recovery"] = run_upcoming_dq_recovery(target_pct=target)
        mean_before = mean_runner_dq(load_scored_cards())
        report["mean_dq_before"] = mean_before
        if mean_before >= target:
            report["mean_dq_after"] = mean_before
            report["ok"] = True
            return report
    except Exception as exc:
        report["upcoming_recovery_error"] = str(exc)[:120]

    if os.getenv("HIBS_RACING_ENRICH_RECOVERY", "1").strip().lower() in ("1", "true", "yes", "on"):
        try:
            from hibs_racing.ingest.enrich_backup import run_targeted_enrich_recovery

            min_cov = racing_enrich_recovery_min_pct()
            max_days = int(os.getenv("HIBS_RACING_ENRICH_RECOVERY_DAYS", "120"))
            report["enrich_recovery"] = run_targeted_enrich_recovery(
                min_mean_coverage_pct=min_cov,
                max_days=max_days,
            )
        except Exception as exc:
            report["enrich_recovery_error"] = str(exc)[:120]

    current = mean_before
    for idx in range(passes):
        if current >= target:
            break
        try:
            rescue = run_thin_rescue_pass()
            report[f"thin_rescue_pass_{idx + 1}"] = rescue
            after = mean_runner_dq(load_scored_cards())
            if after <= current and int(rescue.get("rescued") or 0) == 0:
                break
            current = after
        except Exception as exc:
            report[f"thin_rescue_error_{idx + 1}"] = str(exc)[:120]
            break

    mean_after = mean_runner_dq(load_scored_cards())
    report["mean_dq_after"] = mean_after
    report["ok"] = mean_after >= target
    return report
