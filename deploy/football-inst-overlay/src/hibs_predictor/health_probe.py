"""Lightweight latency and scraper-shape probes for the dashboard health panel."""

import json
import os
import time
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv

from hibs_predictor.data_aggregator import _env_first_usable
from hibs_predictor.scraper_health import http_status_from_exc, scraper_error_code, scraper_row
from hibs_predictor.scrapers.statsbomb_open import OPEN_BASE


def _ms_since(t0: float) -> float:
    return round((time.perf_counter() - t0) * 1000, 1)


def cache_disk_summary() -> Dict[str, Any]:
    """Summarise on-disk JSON cache (TTL metadata + size) for /api/health — no writes."""
    try:
        from hibs_predictor.cache import Cache

        c = Cache()
        root = c.cache_dir
        n_files = 0
        bytes_total = 0
        with_ttl = 0
        if root.exists():
            for path in root.glob("*.json"):
                try:
                    bytes_total += path.stat().st_size
                    n_files += 1
                    with open(path, "r", encoding="utf-8") as fh:
                        data = json.load(fh)
                    if isinstance(data, dict) and data.get("ttl_hours") is not None:
                        with_ttl += 1
                except (OSError, json.JSONDecodeError, TypeError, ValueError):
                    continue
        return {
            "cache_dir": str(root.resolve()),
            "files": n_files,
            "bytes_approx": bytes_total,
            "entries_with_ttl_metadata": with_ttl,
            "ttl_note": "Entries written via Cache.set store cached_at + ttl_hours; prune_stale() removes expired JSON.",
        }
    except Exception as exc:
        return {
            "cache_dir": ".cache",
            "files": 0,
            "bytes_approx": 0,
            "entries_with_ttl_metadata": 0,
            "error": str(exc)[:160],
        }


def gather_health_light() -> Dict[str, Any]:
    """Fast /api/health path — disk cache + audit_ops only (no live API/scraper probes)."""
    from hibs_predictor.health_quality_narrative import _audit_ops_summary

    return {
        "mode": "light",
        "apis": [],
        "scrapers": [],
        "cache_disk": cache_disk_summary(),
        "audit_ops": _audit_ops_summary(),
        "prediction_quality": {
            "overall": "light",
            "headline": "Light health — live API probes skipped (use full /api/health for scraper panel).",
            "bullets": [],
        },
    }


def gather_health() -> Dict[str, Any]:
    """Return API latencies and scraper status for /api/health (best-effort, no crash)."""
    load_dotenv()
    apis: List[Dict[str, Any]] = []
    scrapers: List[Dict[str, Any]] = []

    # --- API-Football (timezone is small + requires key; same env resolution as DataAggregator) ---
    key = _env_first_usable("API_SPORTS_FOOTBALL_KEY", "API_SPORTS_KEY", "APISPORTS_KEY")
    t0 = time.perf_counter()
    if key:
        try:
            r = requests.get(
                "https://v3.football.api-sports.io/timezone",
                headers={"x-apisports-key": key},
                timeout=15,
            )
            ms = _ms_since(t0)
            ok = r.status_code == 200
            apis.append(
                {
                    "id": "api_football",
                    "label": "API-Football",
                    "ms": ms,
                    "ok": ok,
                    "error": None if ok else f"HTTP {r.status_code}",
                }
            )
        except Exception as exc:
            apis.append(
                {
                    "id": "api_football",
                    "label": "API-Football",
                    "ms": None,
                    "ok": False,
                    "error": str(exc)[:160],
                }
            )
    else:
        apis.append(
            {
                "id": "api_football",
                "label": "API-Football",
                "ms": None,
                "ok": False,
                "error": "API_SPORTS_FOOTBALL_KEY / API_SPORTS_KEY / APISPORTS_KEY not set",
            }
        )

    # --- Football-Data.org (cached probe — respect 10 req/min) ---
    fdo = _env_first_usable("FOOTBALL_DATA_ORG_KEY", "FOOTBALL_DATA_KEY")
    fdo_probe_ttl_min = 30.0
    try:
        fdo_probe_ttl_min = max(5.0, float(os.getenv("HIBS_FOOTBALL_DATA_HEALTH_PROBE_MIN", "30")))
    except ValueError:
        pass
    fdo_cached_ok: Optional[bool] = None
    fdo_cached_err: Optional[str] = None
    if fdo:
        try:
            from hibs_predictor.cache import Cache

            probe_row = Cache().get("health_probe_football_data_org", ttl_hours=fdo_probe_ttl_min / 60.0)
            if isinstance(probe_row, dict) and "ok" in probe_row:
                fdo_cached_ok = bool(probe_row.get("ok"))
                fdo_cached_err = probe_row.get("error")
        except Exception:
            pass
    t0 = time.perf_counter()
    if fdo:
        if fdo_cached_ok is not None:
            apis.append(
                {
                    "id": "football_data_org",
                    "label": "Football-Data.org",
                    "ms": None,
                    "ok": fdo_cached_ok,
                    "error": fdo_cached_err,
                }
            )
        else:
            try:
                from hibs_predictor.api_clients import (
                    football_data_record_request,
                    football_data_requests_allowed,
                    football_data_trip_minute_guard,
                )

                if not football_data_requests_allowed():
                    apis.append(
                        {
                            "id": "football_data_org",
                            "label": "Football-Data.org",
                            "ms": None,
                            "ok": False,
                            "error": "local rate guard (10 req/min)",
                        }
                    )
                else:
                    r = requests.get(
                        "https://api.football-data.org/v4/competitions",
                        headers={"X-Auth-Token": fdo},
                        timeout=15,
                    )
                    ms = _ms_since(t0)
                    ok = r.status_code == 200
                    err = None if ok else f"HTTP {r.status_code}"
                    apis.append(
                        {
                            "id": "football_data_org",
                            "label": "Football-Data.org",
                            "ms": ms,
                            "ok": ok,
                            "error": err,
                        }
                    )
                    try:
                        from hibs_predictor.cache import Cache

                        football_data_record_request()
                        if r.status_code == 429:
                            football_data_trip_minute_guard()
                        Cache().set(
                            "health_probe_football_data_org",
                            {"ok": ok, "error": err},
                            ttl_hours=fdo_probe_ttl_min / 60.0,
                        )
                    except Exception:
                        pass
            except Exception as exc:
                apis.append(
                    {
                        "id": "football_data_org",
                        "label": "Football-Data.org",
                        "ms": None,
                        "ok": False,
                        "error": str(exc)[:160],
                    }
                )
    else:
        apis.append(
            {
                "id": "football_data_org",
                "label": "Football-Data.org",
                "ms": None,
                "ok": False,
                "error": "not configured",
            }
        )

    # --- The Odds API ---
    odds_key = os.getenv("ODDS_API_KEY", "")
    t0 = time.perf_counter()
    if odds_key:
        try:
            r = requests.get(
                "https://api.the-odds-api.com/v4/sports/",
                params={"apiKey": odds_key},
                timeout=15,
            )
            ms = _ms_since(t0)
            ok = r.status_code == 200
            apis.append(
                {
                    "id": "odds_api",
                    "label": "The Odds API",
                    "ms": ms,
                    "ok": ok,
                    "error": None if ok else f"HTTP {r.status_code}",
                }
            )
        except Exception as exc:
            apis.append(
                {
                    "id": "odds_api",
                    "label": "The Odds API",
                    "ms": None,
                    "ok": False,
                    "error": str(exc)[:160],
                }
            )
    else:
        apis.append(
            {
                "id": "odds_api",
                "label": "The Odds API",
                "ms": None,
                "ok": False,
                "error": "not configured",
            }
        )

    # --- StatsBomb open-data (GitHub raw) ---
    t0 = time.perf_counter()
    try:
        r = requests.get(f"{OPEN_BASE}/competitions.json", timeout=20)
        ms = _ms_since(t0)
        ok = r.status_code == 200
        data = r.json() if ok and r.content else []
        n = len(data) if isinstance(data, list) else 0
        if ok and n > 0:
            scrapers.append(scraper_row(sid="statsbomb_open", label="StatsBomb (open)", ms=ms, ok=True))
        elif ok:
            scrapers.append(
                scraper_row(
                    sid="statsbomb_open",
                    label="StatsBomb (open)",
                    ms=ms,
                    ok=False,
                    error="Empty or invalid competitions payload",
                    layout_broken=True,
                )
            )
        else:
            scrapers.append(
                scraper_row(
                    sid="statsbomb_open",
                    label="StatsBomb (open)",
                    ms=ms,
                    ok=False,
                    error=f"HTTP {r.status_code}",
                    http_status=r.status_code,
                )
            )
    except Exception as exc:
        msg = str(exc)
        layout = "LAYOUT_BROKEN" in msg.upper()
        scrapers.append(
            scraper_row(
                sid="statsbomb_open",
                label="StatsBomb (open)",
                ms=None,
                ok=False,
                error=msg[:160],
                http_status=http_status_from_exc(exc),
                layout_broken=layout,
            )
        )

    # --- Understat (AJAX league data; try current + previous season) ---
    t0 = time.perf_counter()
    try:
        from datetime import date

        from hibs_predictor.scrapers.understat_client import fetch_league_matches

        rows: List[Dict[str, Any]] = []
        for y in (date.today().year, date.today().year - 1):
            rows = fetch_league_matches("EPL", y)
            if len(rows) > 20:
                break
        ms = _ms_since(t0)
        ok = len(rows) > 20
        scrapers.append(
            scraper_row(
                sid="understat",
                label="Understat",
                ms=ms,
                ok=ok,
                error=None if ok else f"League AJAX returned {len(rows)} rows (expected 20+)",
                layout_broken=not ok,
            )
        )
    except Exception as exc:
        msg = str(exc)
        scrapers.append(
            scraper_row(
                sid="understat",
                label="Understat",
                ms=_ms_since(t0),
                ok=False,
                error=msg[:160],
                http_status=http_status_from_exc(exc),
                layout_broken="LAYOUT_BROKEN" in msg.upper(),
            )
        )

    # --- Sofascore public search (light; often 403 off residential IP too) ---
    t0 = time.perf_counter()
    try:
        from hibs_predictor.scrapers import sofascore_client as ss

        hit, blocked = ss.probe_team_search("Arsenal")
        ms = _ms_since(t0)
        if hit:
            scrapers.append(scraper_row(sid="sofascore", label="Sofascore", ms=ms, ok=True))
        elif blocked:
            scrapers.append(
                scraper_row(
                    sid="sofascore",
                    label="Sofascore",
                    ms=ms,
                    ok=False,
                    blocked=True,
                    error="HTTP 403 — API blocked from this network (optional; core 1X2 unaffected)",
                )
            )
        else:
            scrapers.append(
                scraper_row(
                    sid="sofascore",
                    label="Sofascore",
                    ms=ms,
                    ok=False,
                    error="empty search result",
                )
            )
    except Exception as exc:
        msg = str(exc)
        scrapers.append(
            scraper_row(
                sid="sofascore",
                label="Sofascore",
                ms=_ms_since(t0),
                ok=False,
                error=msg[:160],
                http_status=http_status_from_exc(exc),
                blocked="403" in msg,
                layout_broken="LAYOUT_BROKEN" in msg.upper(),
            )
        )

    # --- FotMob daily matches (date + timezone) ---
    t0 = time.perf_counter()
    try:
        from hibs_predictor.scrapers.fotmob_client import probe_matches_api

        pr = probe_matches_api()
        ms = _ms_since(t0)
        ok = bool(pr.get("ok"))
        http_status = pr.get("http_status")
        try:
            http_status = int(http_status) if http_status is not None else None
        except (TypeError, ValueError):
            http_status = None
        scrapers.append(
            scraper_row(
                sid="fotmob",
                label="FotMob",
                ms=ms,
                ok=ok,
                error=None if ok else pr.get("error") or f"leagues={pr.get('league_count', 0)}",
                http_status=http_status,
                layout_broken=not ok and http_status in (None, 200),
            )
        )
    except Exception as exc:
        scrapers.append(
            scraper_row(
                sid="fotmob",
                label="FotMob",
                ms=_ms_since(t0),
                ok=False,
                error=str(exc)[:160],
                http_status=http_status_from_exc(exc),
            )
        )

    # --- FBref squad table (EPL sample; heavy scraper path) ---
    t0 = time.perf_counter()
    try:
        from hibs_predictor.scrapers.fbref_client import probe_squad_table

        pr = probe_squad_table("EPL")
        ms = _ms_since(t0)
        blocked = bool(pr.get("blocked"))
        ok = bool(pr.get("ok"))
        scrapers.append(
            scraper_row(
                sid="fbref",
                label="FBref",
                ms=ms,
                ok=ok,
                error=pr.get("error"),
                blocked=blocked,
                http_status=pr.get("http_status"),
                layout_broken=not ok and not blocked and not pr.get("skipped_env"),
            )
        )
    except Exception as exc:
        scrapers.append(
            scraper_row(
                sid="fbref",
                label="FBref",
                ms=_ms_since(t0),
                ok=False,
                error=str(exc)[:160],
                http_status=http_status_from_exc(exc),
                layout_broken="LAYOUT_BROKEN" in str(exc).upper(),
            )
        )

    # --- SoccerStats latest.asp ---
    t0 = time.perf_counter()
    try:
        from hibs_predictor.scrapers.soccerstats_standings import fetch_league_table

        rows = fetch_league_table("EPL")
        ms = _ms_since(t0)
        ok = len(rows) >= 10
        scrapers.append(
            scraper_row(
                sid="soccerstats",
                label="SoccerStats",
                ms=ms,
                ok=ok,
                error=None if ok else f"rows={len(rows)}",
                layout_broken=not ok,
            )
        )
    except Exception as exc:
        scrapers.append(
            scraper_row(
                sid="soccerstats",
                label="SoccerStats",
                ms=_ms_since(t0),
                ok=False,
                error=str(exc)[:160],
                http_status=http_status_from_exc(exc),
            )
        )

    # --- Deferred / probe-only sources ---
    for sid, label, mod_path, fn in (
        ("transfermarkt", "Transfermarkt", "hibs_predictor.scrapers.transfermarkt_client", "probe_availability"),
        ("xgstat", "xGStat", "hibs_predictor.scrapers.xgstat_client", "probe_public_api"),
        ("besoccer", "BeSoccer", "hibs_predictor.scrapers.besoccer_client", "probe_public_api"),
    ):
        t0 = time.perf_counter()
        try:
            import importlib

            mod = importlib.import_module(mod_path)
            pr = getattr(mod, fn)()
            ms = _ms_since(t0)
            deferred = str(pr.get("status") or "") in ("deferred", "not_available")
            ok = bool(pr.get("ok")) and not deferred
            scrapers.append(
                scraper_row(
                    sid=sid,
                    label=label,
                    ms=ms,
                    ok=ok,
                    error=pr.get("note") or pr.get("error"),
                    deferred=deferred,
                )
            )
        except Exception as exc:
            scrapers.append(
                scraper_row(
                    sid=sid,
                    label=label,
                    ms=_ms_since(t0),
                    ok=False,
                    error=str(exc)[:160],
                    http_status=http_status_from_exc(exc),
                )
            )

    try:
        from hibs_predictor.scrapers.scraper_six import scraper_six_plan_summary

        scraper_six = scraper_six_plan_summary()
    except Exception:
        scraper_six = None

    return {
        "apis": apis,
        "scrapers": scrapers,
        "scraper_six_plan": scraper_six,
        "latency_ok_ms": 200,
        "cache_disk": cache_disk_summary(),
    }
