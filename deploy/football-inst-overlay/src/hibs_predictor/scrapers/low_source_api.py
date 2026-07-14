"""Scrape-only HTTP API for low-source fixture data (no API-Sports burn).

Mirrors hibs-racing ``/api/runner/<id>?rescue=1``: field ladders + optional thin-data
rescue via FotMob, FPL, SoccerStats, Understat, and related scrapers.

Headless automation: ``run_low_source_scrape_cycle()`` + ``scripts/warm_low_source_scrape.sh``.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from hibs_predictor.fixture_utils import fixture_team_name

LOW_SOURCE_CACHE_VERSION = "v1"


def fixture_key(fixture: Dict[str, Any]) -> str:
    home = fixture_team_name(fixture, "home")
    away = fixture_team_name(fixture, "away")
    return f"{home}|{away}|{fixture.get('date', '')}"


def fixture_label(home: str, away: str) -> str:
    return f"{home.strip()} v {away.strip()}"


def _parse_fixture_key_target(fixture_key: str) -> Tuple[str, str, Optional[str]]:
    """Return (home, away, date_or_none) from pipe or ``home v away`` keys."""
    raw = (fixture_key or "").strip()
    if "|" in raw:
        parts = raw.split("|")
        if len(parts) >= 2:
            home = parts[0].strip()
            away = parts[1].strip()
            date_s = parts[2].strip() if len(parts) > 2 and parts[2].strip() else None
            return home, away, date_s
    if " v " in raw.casefold():
        idx = raw.casefold().index(" v ")
        home = raw[:idx].strip()
        away = raw[idx + 3 :].strip()
        return home, away, None
    return raw, "", None


def _fixture_matches_key(fixture: Dict[str, Any], fixture_key: str) -> bool:
    home_t, away_t, date_t = _parse_fixture_key_target(fixture_key)
    if not home_t:
        return False
    home = fixture_team_name(fixture, "home")
    away = fixture_team_name(fixture, "away")
    if home.casefold() != home_t.casefold():
        return False
    if away_t and away.casefold() != away_t.casefold():
        return False
    if date_t:
        fix_date = str(fixture.get("date") or "")
        if date_t not in fix_date:
            return False
    return True


def find_fixture_in_rows(rows: List[Dict[str, Any]], fixture_key: str) -> Optional[Dict[str, Any]]:
    for row in rows:
        if isinstance(row, dict) and _fixture_matches_key(row, fixture_key):
            return row
    return None


def scrape_status_payload() -> Dict[str, Any]:
    from hibs_predictor.scrape_first import scrape_first_status
    from hibs_predictor.scrapers.multi_scraper_api import catalog_summary
    from hibs_predictor.scrapers.robust_odds_scrape import odds_rescue_enabled
    from hibs_predictor.scrapers.scrape_resilience import scrape_resilience_status
    from hibs_predictor.scrapers.source_registry import sources_by_status

    wired = sources_by_status("wired")
    return {
        "ok": True,
        "product": "hibs-bet",
        "mode": "scrape_only",
        "scrape_first": scrape_first_status(),
        "field_ladders": catalog_summary()["field_ladders"],
        "targeted_overflow": catalog_summary().get("targeted_overflow") or [],
        "wired_source_ids": [str(s.get("id")) for s in wired],
        "wired_source_count": len(wired),
        "odds_rescue_enabled": odds_rescue_enabled(),
        "resilience": scrape_resilience_status(),
        "football_data_guard": __import__(
            "hibs_predictor.football_data_guard", fromlist=["status_payload"]
        ).status_payload(),
    }


def fetch_scrape_only_fixtures(
    league_code: str,
    *,
    aggregator: Any,
    allow_stale: bool = False,
) -> List[Dict[str, Any]]:
    """Fixture list from Football-Data.org, FotMob, and ESPN only (no API-Sports)."""
    from hibs_predictor.cache import Cache
    from hibs_predictor.config import LEAGUES
    from hibs_predictor.web import (
        _fixture_fetch_season_candidates,
        _fixture_window_days_for_league,
        _normalize_fdo,
        _normalize_fotmob,
        fixture_window_end_utc,
        fixture_window_start_utc,
    )

    days = _fixture_window_days_for_league(league_code)
    cache = Cache()
    cache_key = f"scrape_fixtures_{days}d_{league_code}"
    if not allow_stale:
        hit = cache.get(cache_key, ttl_hours=1.0)
        if isinstance(hit, list) and hit:
            return hit

    league = LEAGUES.get(league_code, {})
    now = datetime.now(timezone.utc)
    window_start = fixture_window_start_utc(now)
    cutoff = fixture_window_end_utc(now, days)
    fetched: Dict[str, Dict[str, Any]] = {}
    date_from = window_start.strftime("%Y-%m-%d")
    date_to = cutoff.strftime("%Y-%m-%d")
    fdo_comp = league.get("football_data_org_id")
    season_candidates = _fixture_fetch_season_candidates(
        fdo_comp, date_from, date_to, now, league_code=league_code
    )

    def add(candidate: Dict[str, Any]) -> None:
        key = fixture_key(candidate)
        if key and key not in fetched:
            fetched[key] = candidate

    def try_football_data() -> None:
        if "football_data_org" not in aggregator.clients:
            return
        from hibs_predictor.football_data_guard import football_data_traffic_allowed

        comp = league.get("football_data_org_id")
        if not comp or not football_data_traffic_allowed(str(comp)):
            return
        for season in season_candidates:
            try:
                import time as _time

                _time.sleep(0.35)
                raw = aggregator.clients["football_data_org"].fetch_fixtures(
                    comp,
                    season,
                    status=None,
                    date_from=date_from,
                    date_to=date_to,
                )
                for m in raw or []:
                    st = str(m.get("status") or "").upper()
                    norm = _normalize_fdo(m, league_code)
                    if not norm:
                        continue
                    try:
                        fd = datetime.fromisoformat(str(norm["date"]).replace("Z", "+00:00"))
                    except Exception:
                        continue
                    if st in ("CANCELLED", "POSTPONED", "ABANDONED", "SUSPENDED"):
                        continue
                    if st in ("FINISHED", "AWARDED") and fd < window_start:
                        continue
                    if window_start <= fd <= cutoff:
                        norm["date"] = fd.isoformat()
                        norm["source"] = norm.get("source") or "football_data_org"
                        add(norm)
                if fetched:
                    break
            except Exception:
                continue

    def try_fotmob() -> None:
        import os

        if os.getenv("HIBS_ENABLE_FOTMOB_FIXTURES", "1").strip().lower() in ("0", "false", "no", "off"):
            return
        try:
            from hibs_predictor.scrapers import fotmob_client

            raw = fotmob_client.fixtures_for_league(league_code, now.date(), cutoff.date(), cache=cache)
            for m in raw or []:
                norm = _normalize_fotmob(m, league_code)
                if not norm:
                    continue
                try:
                    fd = datetime.fromisoformat(str(norm["date"]).replace("Z", "+00:00"))
                    if window_start <= fd <= cutoff:
                        norm["date"] = fd.isoformat()
                        add(norm)
                except Exception:
                    continue
        except Exception:
            pass

    def try_espn() -> None:
        try:
            from hibs_predictor.scrapers.espn_client import espn_fixtures_enabled, fixtures_for_league

            if not espn_fixtures_enabled():
                return
            for norm in fixtures_for_league(league_code, window_start.date(), cutoff.date(), cache=cache) or []:
                try:
                    fd = datetime.fromisoformat(str(norm.get("date") or "").replace("Z", "+00:00"))
                    if window_start <= fd <= cutoff:
                        norm["date"] = fd.isoformat()
                        add(norm)
                except Exception:
                    continue
        except Exception:
            pass

    try_football_data()
    if not fetched:
        try_fotmob()
    if not fetched:
        try_espn()
    else:
        try_fotmob()
        try_espn()

    rows = sorted(fetched.values(), key=lambda r: str(r.get("date") or ""))
    if rows:
        cache.set(cache_key, rows, ttl_hours=1.0)
    return rows


def _public_field_keys() -> Tuple[str, ...]:
    return (
        "fixture",
        "home",
        "away",
        "date",
        "league",
        "source",
        "home_recent_n",
        "away_recent_n",
        "home_form",
        "away_form",
        "home_stats",
        "away_stats",
        "home_position",
        "away_position",
        "xg_home",
        "xg_away",
        "xg_source",
        "odds_available",
        "odds_home",
        "odds_draw",
        "odds_away",
        "thin_data_rescue",
        "supplemental",
        "data_quality",
    )


def _sources_used(enriched: Dict[str, Any]) -> List[str]:
    used: List[str] = []
    src = str(enriched.get("source") or "").strip()
    if src:
        used.append(src)
    rescue = enriched.get("thin_data_rescue")
    if isinstance(rescue, dict):
        for key in ("home_recent_source", "away_recent_source"):
            v = rescue.get(key)
            if v and v not in used:
                used.append(str(v))
        for part in rescue.get("applied") or []:
            if part and part not in used:
                used.append(str(part))
    xg_src = str(enriched.get("xg_source") or "").strip()
    if xg_src and xg_src not in used:
        used.append(xg_src)
    sup = enriched.get("supplemental")
    if isinstance(sup, dict):
        for k, v in sup.items():
            if v and k not in used:
                used.append(str(k))
    return used


def enrich_low_source(
    fixture: Dict[str, Any],
    league_code: str,
    aggregator: Any,
    *,
    rescue: bool = False,
) -> Dict[str, Any]:
    """Enrich via aggregator + scrapers; bypasses API rate-guard short-circuit."""
    enriched = aggregator.enrich_fixture(fixture, league_code)
    enriched.setdefault("league", league_code)
    if rescue:
        from hibs_predictor.fixture_utils import fixture_team_id
        from hibs_predictor.scrapers.thin_data_rescue import apply_thin_data_rescue

        enriched = apply_thin_data_rescue(
            enriched,
            fixture,
            league_code,
            home_id=fixture_team_id(fixture, "home"),
            away_id=fixture_team_id(fixture, "away"),
            supplemental=enriched.get("supplemental"),
            force=True,
        )
    from hibs_predictor.data_quality import compute_fixture_data_quality

    enriched["data_quality"] = compute_fixture_data_quality(enriched)
    enriched["data_quality_pct"] = (enriched.get("data_quality") or {}).get("score_pct")
    if rescue and os.getenv("HIBS_ROBUST_ODDS_SCRAPE", "1").strip().lower() in ("1", "true", "yes", "on"):
        try:
            from hibs_predictor.scrapers.robust_odds_scrape import rescue_fixture_odds

            enriched = rescue_fixture_odds(aggregator, fixture, league_code, enriched=enriched)
        except Exception:
            pass
    return enriched


def build_fixture_payload(
    fixture: Dict[str, Any],
    enriched: Dict[str, Any],
    *,
    league_code: str,
    rescued: bool = False,
) -> Dict[str, Any]:
    from hibs_predictor.assistant_context import thin_data_flags
    from hibs_predictor.scrapers.multi_scraper_api import FIELD_LADDERS

    home = fixture_team_name(fixture, "home")
    away = fixture_team_name(fixture, "away")
    dq = enriched.get("data_quality") or {}
    flags = thin_data_flags(enriched)
    return {
        "ok": True,
        "fixture_key": fixture_key(fixture),
        "fixture_label": fixture_label(home, away),
        "league": league_code,
        "kickoff_iso": fixture.get("date"),
        "data_quality_pct": dq.get("score_pct"),
        "blocks": dq.get("blocks") or [],
        "thin_data": "thin_data" in flags,
        "thin_data_flags": flags,
        "field_ladders": FIELD_LADDERS,
        "fields": {k: enriched.get(k) for k in _public_field_keys()},
        "sources_used": _sources_used(enriched),
        "rescued": bool(rescued),
        "fixture_source": fixture.get("source"),
    }


def resolve_fixture_low_source(
    fixture_key: str,
    league_code: str,
    aggregator: Any,
    *,
    rescue: bool = False,
    bundle_loader: Optional[Callable[[], Dict[str, Any]]] = None,
) -> Optional[Dict[str, Any]]:
    """Lookup one fixture and return scrape-enriched low-source payload."""
    rows = fetch_scrape_only_fixtures(league_code, aggregator=aggregator)
    match = find_fixture_in_rows(rows, fixture_key)
    if not match and bundle_loader is not None:
        bundle = bundle_loader() or {}
        match = find_fixture_in_rows(bundle.get("all") or [], fixture_key)
    if not match:
        return None
    enriched = enrich_low_source(match, league_code, aggregator, rescue=rescue)
    return build_fixture_payload(match, enriched, league_code=league_code, rescued=rescue)


def list_fixtures_payload(
    league_code: str,
    aggregator: Any,
    *,
    enrich: bool = False,
    rescue: bool = False,
) -> Dict[str, Any]:
    rows = fetch_scrape_only_fixtures(league_code, aggregator=aggregator)
    if not enrich:
        slim = []
        for row in rows:
            home = fixture_team_name(row, "home")
            away = fixture_team_name(row, "away")
            slim.append(
                {
                    "fixture_key": fixture_key(row),
                    "fixture_label": fixture_label(home, away),
                    "kickoff_iso": row.get("date"),
                    "source": row.get("source"),
                    "status": ((row.get("fixture") or {}).get("status") or {}).get("short"),
                }
            )
        return {
            "ok": True,
            "league": league_code,
            "mode": "scrape_only",
            "count": len(slim),
            "fixtures": slim,
        }
    enriched_rows = []
    for row in rows:
        enriched = enrich_low_source(row, league_code, aggregator, rescue=rescue)
        enriched_rows.append(build_fixture_payload(row, enriched, league_code=league_code, rescued=rescue))
    thin_n = sum(1 for r in enriched_rows if r.get("thin_data"))
    return {
        "ok": True,
        "league": league_code,
        "mode": "scrape_only_enriched",
        "count": len(enriched_rows),
        "thin_data_count": thin_n,
        "fixtures": enriched_rows,
    }


def _env_truthy(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


def _low_source_league_codes() -> List[str]:
    extra = (os.getenv("HIBS_LOW_SOURCE_SCRAPE_LEAGUES") or "").strip()
    if extra:
        return [c.strip().upper() for c in extra.split(",") if c.strip()]
    from hibs_predictor.tournament_focus import active_competition_league_codes

    return list(active_competition_league_codes())


def _low_source_cache_key(league_code: str) -> str:
    return f"low_source_scrape_{LOW_SOURCE_CACHE_VERSION}_{league_code}"


def _enrich_max_per_cycle() -> int:
    try:
        return max(1, int(os.getenv("HIBS_LOW_SOURCE_ENRICH_MAX", "25")))
    except ValueError:
        return 25


def _bundle_fixture_count(include_domestic: bool = False) -> int:
    from hibs_predictor.cache import Cache
    from hibs_predictor.web import _all_fixtures_cache_key, _is_complete_fixture_bundle

    peek = Cache().peek(_all_fixtures_cache_key(include_domestic=include_domestic))
    if not isinstance(peek, dict) or not _is_complete_fixture_bundle(peek):
        return 0
    return len(peek.get("all") or [])


def maybe_backfill_fixture_bundle(
    enriched_rows: List[Dict[str, Any]],
    aggregator: Any,
    *,
    include_domestic: bool = False,
    force: bool = False,
) -> Dict[str, Any]:
    """Merge scrape-enriched rows into the main disk bundle when empty or forced."""
    out: Dict[str, Any] = {"backfilled": False, "merged": 0, "bundle_count": 0}
    if not enriched_rows:
        return out
    if not force and not _env_truthy("HIBS_LOW_SOURCE_BACKFILL_BUNDLE", "1"):
        return out
    try:
        from hibs_predictor.scrape_first import scrape_first_mode

        if not force and not scrape_first_mode():
            return out
    except Exception:
        pass

    existing_n = _bundle_fixture_count(include_domestic=include_domestic)
    min_rows = 1
    try:
        min_rows = max(0, int(os.getenv("HIBS_LOW_SOURCE_BACKFILL_MIN_BUNDLE", "1")))
    except ValueError:
        pass
    if not force and existing_n >= min_rows:
        out["bundle_count"] = existing_n
        out["skipped"] = "bundle_already_populated"
        return out

    from hibs_predictor.cache import Cache
    from hibs_predictor.web import (
        _all_fixtures_cache_key,
        _cache_ttl_hours,
        _finalize_fixture_bundle,
        _fixture_key,
    )

    cache = Cache()
    ck = _all_fixtures_cache_key(include_domestic=include_domestic)
    peek = cache.peek(ck)
    existing = list((peek.get("all") or []) if isinstance(peek, dict) else [])
    seen = {_fixture_key(r) for r in existing if isinstance(r, dict)}
    merged_new: List[Dict[str, Any]] = []
    for row in enriched_rows:
        if not isinstance(row, dict):
            continue
        key = _fixture_key(row)
        if key and key not in seen:
            merged_new.append(row)
            seen.add(key)
    if not merged_new and existing:
        out["bundle_count"] = len(existing)
        out["skipped"] = "no_new_rows"
        return out

    all_rows = existing + merged_new
    bundle = _finalize_fixture_bundle(
        all_rows,
        attach_live=False,
        include_domestic=include_domestic,
        reboost=False,
    )
    cache.set(ck, bundle, ttl_hours=_cache_ttl_hours(1.0))
    out.update(
        {
            "backfilled": True,
            "merged": len(merged_new),
            "bundle_count": len(bundle.get("all") or []),
        }
    )
    return out


def run_low_source_scrape_cycle(
    aggregator: Any,
    *,
    enrich: Optional[bool] = None,
    rescue: bool = True,
    backfill_bundle: Optional[bool] = None,
    include_domestic: bool = False,
    force: bool = False,
) -> Dict[str, Any]:
    """Headless scrape cycle for cron / hands-off repair (no HTTP)."""
    from hibs_predictor.cache import Cache
    from hibs_predictor.scrape_first import scrape_first_status

    t0 = datetime.now(timezone.utc)
    leagues = _low_source_league_codes()
    do_enrich = enrich if enrich is not None else _env_truthy("HIBS_LOW_SOURCE_AUTO_ENRICH", "1")
    do_backfill = backfill_bundle if backfill_bundle is not None else _env_truthy(
        "HIBS_LOW_SOURCE_BACKFILL_BUNDLE", "1"
    )
    cache = Cache()
    report: Dict[str, Any] = {
        "ok": True,
        "at": t0.isoformat(),
        "mode": "low_source_scrape_cycle",
        "scrape_first": scrape_first_status(),
        "leagues": leagues,
        "enrich": do_enrich,
        "rescue": rescue,
        "per_league": {},
        "fixture_count": 0,
        "enriched_count": 0,
        "thin_data_count": 0,
    }

    enriched_all: List[Dict[str, Any]] = []
    enrich_budget = _enrich_max_per_cycle()
    for league_code in leagues:
        league_report: Dict[str, Any] = {"fetched": 0, "enriched": 0, "thin": 0}
        try:
            rows = fetch_scrape_only_fixtures(
                league_code,
                aggregator=aggregator,
                allow_stale=not force,
            )
        except Exception as exc:
            league_report["error"] = str(exc)[:160]
            report["per_league"][league_code] = league_report
            continue

        league_report["fetched"] = len(rows)
        cache.set(_low_source_cache_key(league_code), rows, ttl_hours=2.0)

        if do_enrich and rows:
            for fix in rows:
                if enrich_budget <= 0:
                    league_report["enrich_capped"] = True
                    break
                try:
                    row = enrich_low_source(fix, league_code, aggregator, rescue=rescue)
                    row.setdefault("league", league_code)
                    enriched_all.append(row)
                    enrich_budget -= 1
                    league_report["enriched"] += 1
                    if (row.get("data_quality") or {}).get("score_pct", 100) < 70:
                        league_report["thin"] += 1
                except Exception as exc:
                    league_report.setdefault("enrich_errors", []).append(str(exc)[:80])

        report["per_league"][league_code] = league_report
        report["fixture_count"] += league_report["fetched"]

    report["enriched_count"] = len(enriched_all)
    report["thin_data_count"] = sum(
        1
        for r in enriched_all
        if float((r.get("data_quality") or {}).get("score_pct") or 0) < 70
    )

    if enriched_all and _env_truthy("HIBS_ROBUST_ODDS_SCRAPE", "1"):
        try:
            from hibs_predictor.scrapers.robust_odds_scrape import odds_coverage_summary, run_odds_rescue_pass

            odds_pass = run_odds_rescue_pass(aggregator, enriched_all)
            enriched_all = odds_pass.get("rows", enriched_all)
            report["odds_rescue"] = {k: v for k, v in odds_pass.items() if k != "rows"}
            cov = odds_pass.get("coverage") or odds_coverage_summary(enriched_all)
            report["odds_coverage_pct"] = cov.get("coverage_pct")
            report["with_1x2_odds"] = cov.get("with_odds")
        except Exception as exc:
            report["odds_rescue_error"] = str(exc)[:120]

    if do_backfill and enriched_all:
        bundle_n = _bundle_fixture_count(include_domestic=include_domestic)
        report["bundle_count_before"] = bundle_n
        backfill = maybe_backfill_fixture_bundle(
            enriched_all,
            aggregator,
            include_domestic=include_domestic,
            force=force or bundle_n == 0,
        )
        report["backfill"] = backfill

    elapsed = (datetime.now(timezone.utc) - t0).total_seconds()
    report["elapsed_sec"] = round(elapsed, 2)
    try:
        from hibs_predictor.scrapers.scrape_resilience import scrape_resilience_status

        report["resilience"] = scrape_resilience_status()
    except Exception:
        pass
    if report["fixture_count"] == 0 and not force:
        report["ok"] = False
        report["error"] = "no_scrape_fixtures"
    return report
