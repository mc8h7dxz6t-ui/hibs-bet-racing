"""Inst++ data producer SLO — football cache, FVE export, racing freshness."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from urllib import error, request


def _utc_today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _env_truthy(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, "")
    if not raw:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def probe_http_json(url: str, *, timeout: float = 5.0) -> Dict[str, Any]:
    t0 = time.perf_counter()
    try:
        req = request.Request(url, headers={"User-Agent": "hibs-data-producer-slo/1.0", "Accept": "application/json"})
        with request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            ms = round((time.perf_counter() - t0) * 1000, 1)
            data = json.loads(body) if body.strip() else {}
            return {"ok": True, "status": resp.status, "ms": ms, "data": data if isinstance(data, dict) else {}}
    except error.HTTPError as exc:
        ms = round((time.perf_counter() - t0) * 1000, 1)
        return {"ok": False, "status": exc.code, "ms": ms, "error": f"http_{exc.code}"}
    except Exception as exc:
        ms = round((time.perf_counter() - t0) * 1000, 1)
        return {"ok": False, "status": None, "ms": ms, "error": str(exc)[:120]}


def football_fixture_bundle_status(*, include_domestic: bool = False) -> Dict[str, Any]:
    from hibs_predictor.cache import Cache
    from hibs_predictor.web import _all_fixtures_cache_key, _is_complete_fixture_bundle

    key = _all_fixtures_cache_key(include_domestic=include_domestic)
    cached = Cache().peek(key)
    if not isinstance(cached, dict):
        return {
            "ok": False,
            "cache_hit": False,
            "fixture_count": 0,
            "bundle_complete": False,
            "cache_age_hours": None,
            "with_1x2_odds": 0,
            "message": "cache_miss",
        }
    rows = cached.get("all") or []
    with_odds = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        bo = row.get("best_odds_1x2") or {}
        if isinstance(bo, dict) and any(bo.get(k) for k in ("home", "draw", "away")):
            with_odds += 1
    age_h: Optional[float] = None
    raw_at = cached.get("cached_at")
    if raw_at:
        try:
            cached_at = datetime.fromisoformat(str(raw_at))
            if cached_at.tzinfo is None:
                cached_at = cached_at.replace(tzinfo=timezone.utc)
            age_h = round((datetime.now(timezone.utc) - cached_at).total_seconds() / 3600.0, 2)
        except (TypeError, ValueError):
            pass
    max_age = float(os.getenv("HIBS_FIXTURE_CACHE_MAX_AGE_HOURS", "6"))
    complete = _is_complete_fixture_bundle(cached)
    fresh = age_h is not None and age_h <= max_age
    ok = complete and len(rows) > 0 and (fresh or age_h is None)
    return {
        "ok": ok,
        "cache_hit": True,
        "fixture_count": len(rows),
        "bundle_complete": complete,
        "cache_age_hours": age_h,
        "max_age_hours": max_age,
        "with_1x2_odds": with_odds,
        "odds_coverage_pct": round(100.0 * with_odds / len(rows), 1) if rows else 0.0,
        "message": "ok" if ok else ("stale" if complete and not fresh else "incomplete_or_empty"),
    }


def fve_lines_export_status() -> Dict[str, Any]:
    from hibs_predictor.fve_lines_proxy import list_fixtures_peek

    peek = list_fixtures_peek(include_domestic=False)
    count = int(peek.get("count") or 0)
    return {
        "ok": count > 0,
        "fixture_count": count,
        "source": peek.get("source"),
        "message": "ok" if count > 0 else "no_fixtures_for_fve_upstream",
    }


def fve_remote_status() -> Dict[str, Any]:
    from hibs_predictor.fve_status import fetch_fve_status

    try:
        st = fetch_fve_status()
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:120]}
    paused = bool(st.get("paused"))
    reachable = bool(st.get("reachable"))
    worker = bool(st.get("worker_live"))
    ok = reachable and not paused and worker
    return {
        "ok": ok,
        "reachable": reachable,
        "paused": paused,
        "worker_live": worker,
        "api_url": st.get("api_url"),
        "message": "ok" if ok else ("paused" if paused else "unreachable_or_worker_down"),
        **{k: st.get(k) for k in ("line_trader_url", "public_ws_url") if st.get(k)},
    }


def racing_card_freshness_status(*, base_url: str = "http://127.0.0.1:5003") -> Dict[str, Any]:
    probe = probe_http_json(f"{base_url.rstrip('/')}/api/health", timeout=20.0)
    scrape_probe = probe_http_json(f"{base_url.rstrip('/')}/api/scrape/status", timeout=12.0)
    resilience_probe = probe_http_json(f"{base_url.rstrip('/')}/api/scrape/resilience", timeout=12.0)
    if not probe.get("ok"):
        return {
            "ok": False,
            "reachable": False,
            "latency_ms": probe.get("ms"),
            "error": probe.get("error"),
            "message": "health_unreachable",
        }
    h = probe.get("data") or {}
    scrape_st = scrape_probe.get("data") if isinstance(scrape_probe.get("data"), dict) else {}
    resil_st = resilience_probe.get("data") if isinstance(resilience_probe.get("data"), dict) else {}
    last_cycle = resil_st.get("last_cycle") if isinstance(resil_st.get("last_cycle"), dict) else {}
    today = _utc_today()
    latest = h.get("latest_card_date")
    card_fresh = h.get("card_fresh")
    if card_fresh is None and latest:
        card_fresh = str(latest) >= today
    runners = int(h.get("runners_loaded") or 0)
    manifest = h.get("manifest_id")
    tel = h.get("telemetry_balance") if isinstance(h.get("telemetry_balance"), dict) else {}
    tel_ok = tel.get("passed")
    cron_ok = (h.get("cron") or {}).get("healthy") if isinstance(h.get("cron"), dict) else None
    odds_pct = last_cycle.get("odds_coverage_pct")
    scrape_ok = scrape_probe.get("ok") is not False
    ok = bool(card_fresh) and runners > 0 and tel_ok is not False and scrape_ok
    return {
        "ok": ok,
        "reachable": True,
        "latency_ms": probe.get("ms"),
        "today_utc": today,
        "latest_card_date": latest,
        "card_fresh": card_fresh,
        "runners_loaded": runners,
        "manifest_id": manifest,
        "telemetry_balance_passed": tel_ok,
        "cron_healthy": cron_ok,
        "production_value_count": h.get("production_value_count"),
        "scrape_first": scrape_st.get("scrape_first"),
        "cards_source": scrape_st.get("cards_source"),
        "odds_coverage_pct": odds_pct,
        "robust_scrape_ok": last_cycle.get("ok"),
        "message": "ok" if ok else "stale_or_thin_card",
    }


def football_health_light_status(*, base_url: str = "http://127.0.0.1:8000") -> Dict[str, Any]:
    probe = probe_http_json(f"{base_url.rstrip('/')}/api/health?light=1", timeout=12.0)
    ok = bool(probe.get("ok")) and float(probe.get("ms") or 999) < 10000
    return {
        "ok": ok,
        "latency_ms": probe.get("ms"),
        "mode": "light",
        "error": probe.get("error"),
    }


def robust_scrape_status() -> Dict[str, Any]:
    try:
        from hibs_predictor.scrape_first import scrape_first_mode
        from hibs_predictor.scrapers.robust_scrape_cycle import robust_scrape_slo_status

        if not scrape_first_mode():
            return {"ok": True, "skipped": True, "message": "not_scrape_first"}
        return robust_scrape_slo_status()
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:120], "message": "robust_scrape_unavailable"}


def build_data_producer_snapshot() -> Dict[str, Any]:
    football_bundle = football_fixture_bundle_status()
    fve_export = fve_lines_export_status()
    fve_remote = fve_remote_status()
    racing = racing_card_freshness_status()
    health_light = football_health_light_status()
    robust_scrape = robust_scrape_status()
    producers = {
        "football_bundle": football_bundle,
        "fve_lines_export": fve_export,
        "fve_remote": fve_remote,
        "racing_cards": racing,
        "football_health_light": health_light,
        "robust_scrape": robust_scrape,
    }
    critical_ok = (
        football_bundle.get("ok")
        and fve_export.get("ok")
        and racing.get("ok")
        and health_light.get("ok")
    )
    scrape_ok = robust_scrape.get("ok") is not False
    fve_ok = fve_remote.get("ok") or (fve_remote.get("reachable") and fve_export.get("ok"))
    return {
        "layer": "data_producer_slo",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "ok": critical_ok and bool(fve_ok) and scrape_ok,
        "critical_ok": critical_ok,
        "fve_ok": fve_ok,
        "producers": producers,
    }


def needs_data_producer_repair(snapshot: Optional[Dict[str, Any]] = None) -> bool:
    snap = snapshot or build_data_producer_snapshot()
    return not bool(snap.get("ok"))
