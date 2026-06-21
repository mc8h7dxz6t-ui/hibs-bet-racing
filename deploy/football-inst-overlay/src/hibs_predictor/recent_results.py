"""Recent finished-match results for dashboard (FT / AET / PEN only — no live polling)."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone, date
from typing import Any, Dict, List, Optional, Tuple

from hibs_predictor.cache import Cache
from hibs_predictor.config import LEAGUES, league_dashboard_region
from hibs_predictor.display_tz import (
    attach_kickoff_display,
    day_heading_for_local_date,
    display_timezone,
    parse_kickoff_utc,
)
from hibs_predictor.fixture_utils import (
    display_competition_title,
    format_goal_scorers_line,
    goal_scorers_from_events,
)
from hibs_predictor.season import CALENDAR_YEAR_LEAGUES
from hibs_predictor.tournament_focus import (
    effective_dashboard_league_order,
    league_codes_for_fetch,
    tournament_focus_active,
)

_RESULTS_CACHE_VERSION = "v1"
_FDO_CALENDAR_COMPS = frozenset({"WC", "EC", "UNL", "CL", "EL", "UECL"})
_API_FIRST_FIXTURE_LEAGUES = frozenset({"UCL", "EUROPA_LEAGUE", "UECL"})
_API_SPORTS_FINISHED = frozenset({"FT", "AET", "PEN"})
_FDO_FINISHED = frozenset({"FINISHED", "AWARDED"})


def _env_truthy(name: str) -> bool:
    return (os.getenv(name) or "").strip().lower() in ("1", "true", "yes", "on")


_EVENTS_CACHE_PREFIX = "api_sports_fixture_events_"
_EVENTS_CACHE_TTL_HOURS = 24.0


def _results_fetch_events() -> bool:
    """Default ON; set HIBS_RESULTS_FETCH_EVENTS=0 to disable fixtures/events calls."""
    raw = os.getenv("HIBS_RESULTS_FETCH_EVENTS", "").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    if raw in ("1", "true", "yes", "on"):
        return True
    return True


def _results_max_event_fetches() -> int:
    try:
        return max(0, min(30, int(os.getenv("HIBS_RESULTS_MAX_EVENT_FETCHES", "12"))))
    except ValueError:
        return 12


def _finished_result_status(row: Dict[str, Any]) -> bool:
    return str(row.get("status") or "").upper() in _API_SPORTS_FINISHED


def _result_has_goals(row: Dict[str, Any]) -> bool:
    try:
        return int(row.get("score_home") or 0) + int(row.get("score_away") or 0) > 0
    except (TypeError, ValueError):
        return False


def _apply_goal_scorers_from_events(row: Dict[str, Any], events: List[Dict[str, Any]]) -> bool:
    scorers = goal_scorers_from_events(events)
    if scorers:
        row["goal_scorers_line"] = format_goal_scorers_line(scorers)
        return True
    return False


def _enrich_goal_scorers(rows: List[Dict[str, Any]], aggregator: Any, cache: Cache) -> None:
    """Attach goal scorers for FT results in the lookback window (cached per fixture 24h)."""
    if not rows:
        return
    client = (getattr(aggregator, "clients", None) or {}).get("api_sports")
    budget = _results_max_event_fetches() if _results_fetch_events() else 0
    rate_limiter = getattr(client, "rate_limiter", None) if client else None
    for row in rows:
        if not _finished_result_status(row):
            continue
        embedded = row.get("events")
        if isinstance(embedded, list) and embedded:
            _apply_goal_scorers_from_events(row, embedded)
            continue
        if not _result_has_goals(row):
            continue
        fid = row.get("id")
        if fid is None or not client:
            continue
        try:
            fid_int = int(fid)
        except (TypeError, ValueError):
            continue
        ck = f"{_EVENTS_CACHE_PREFIX}{fid_int}"
        events = cache.get(ck, ttl_hours=_EVENTS_CACHE_TTL_HOURS)
        if events is None and budget > 0:
            if rate_limiter is not None and not rate_limiter.check_rate_limit("api_sports"):
                break
            try:
                data = client._get_json("fixtures/events", params={"fixture": fid_int}, use_cache=False)
                events = data.get("response") if isinstance(data.get("response"), list) else []
                cache.set(ck, events, ttl_hours=_EVENTS_CACHE_TTL_HOURS)
                budget -= 1
            except Exception:
                events = []
                cache.set(ck, events, ttl_hours=_EVENTS_CACHE_TTL_HOURS)
        if events:
            _apply_goal_scorers_from_events(row, events)


def results_days() -> int:
    try:
        return max(1, min(14, int(os.getenv("HIBS_RESULTS_DAYS", "3"))))
    except ValueError:
        return 3


def _cache_ttl_hours(default: float = 1.0) -> float:
    try:
        return max(0.01, float(os.getenv("HIBS_CACHE_TTL_HOURS", str(default))))
    except ValueError:
        return default


def _api_football_season_year(now: datetime) -> int:
    return now.year if now.month >= 7 else now.year - 1


def _years_touched_by_date_range(date_from_s: str, date_to_s: str) -> List[int]:
    d0 = date.fromisoformat(date_from_s[:10])
    d1 = date.fromisoformat(date_to_s[:10])
    if d1 < d0:
        d0, d1 = d1, d0
    return list(range(d0.year, d1.year + 1))


def _fixture_fetch_season_candidates(
    football_data_comp_id: Optional[str],
    date_from_s: str,
    date_to_s: str,
    now: datetime,
    *,
    league_code: Optional[str] = None,
) -> List[int]:
    primary = _api_football_season_year(now)
    if not football_data_comp_id or football_data_comp_id not in _FDO_CALENDAR_COMPS:
        out = [primary, primary - 1]
        code = (league_code or "").strip().upper()
        if code in CALENDAR_YEAR_LEAGUES and now.month < 7 and now.year not in out:
            out.insert(0, now.year)
        return out
    window_years = _years_touched_by_date_range(date_from_s, date_to_s)
    merged = set(window_years) | {primary, primary - 1}
    out: List[int] = []
    seen: set[int] = set()
    for y in (primary, primary - 1):
        if y in merged and y not in seen:
            out.append(y)
            seen.add(y)
    for y in sorted(window_years, reverse=True):
        if y in merged and y not in seen:
            out.append(y)
            seen.add(y)
    for y in sorted(merged - seen, reverse=True):
        out.append(y)
    return out


def results_window_utc(now: Optional[datetime] = None) -> Tuple[datetime, datetime]:
    """Inclusive UTC window: start of display-TZ day (today - N + 1) through now."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    days = results_days()
    local = now.astimezone(display_timezone())
    start_day = local.date() - timedelta(days=max(0, days - 1))
    start_local = datetime(
        start_day.year, start_day.month, start_day.day, 0, 0, 0, tzinfo=local.tzinfo
    )
    return start_local.astimezone(timezone.utc), now


def _results_cache_key(*, include_domestic: bool = False) -> str:
    focus = "full" if include_domestic else ("intl" if tournament_focus_active() else "all")
    return f"recent_results_{results_days()}d_{focus}_{_RESULTS_CACHE_VERSION}"


def _league_results_cache_key(league_code: str) -> str:
    prefer_fdo = _env_truthy("HIBS_PREFER_FOOTBALL_DATA_FIXTURES")
    skip_as = _env_truthy("HIBS_SKIP_API_SPORTS_FIXTURES")
    return (
        f"results_{results_days()}d_{league_code}_{_RESULTS_CACHE_VERSION}_"
        f"{int(prefer_fdo)}{int(skip_as)}"
    )


def _extract_xg_from_stats_block(block: Dict[str, Any]) -> Optional[float]:
    xg_block = block.get("expected_goals")
    if isinstance(xg_block, dict):
        for key in ("total", "value", "on"):
            raw = xg_block.get(key)
            if raw is None or raw == "":
                continue
            try:
                return float(raw)
            except (TypeError, ValueError):
                continue
    if isinstance(xg_block, (int, float)):
        try:
            return float(xg_block)
        except (TypeError, ValueError):
            return None
    stats = block.get("statistics")
    if isinstance(stats, list):
        for item in stats:
            if not isinstance(item, dict):
                continue
            if str(item.get("type") or "").lower() in ("expected goals", "expected_goals", "xg"):
                val = item.get("value")
                if val is None or val == "":
                    continue
                try:
                    return float(val)
                except (TypeError, ValueError):
                    continue
    return None


def _xg_from_api_sports_row(raw: Dict[str, Any]) -> Tuple[Optional[float], Optional[float]]:
    stats_list = raw.get("statistics")
    if not isinstance(stats_list, list):
        return None, None
    home_id = (raw.get("teams") or {}).get("home", {}).get("id")
    away_id = (raw.get("teams") or {}).get("away", {}).get("id")
    home_xg: Optional[float] = None
    away_xg: Optional[float] = None
    for block in stats_list:
        if not isinstance(block, dict):
            continue
        team_id = (block.get("team") or {}).get("id")
        xg_val = _extract_xg_from_stats_block(block)
        if xg_val is None:
            continue
        if team_id == home_id:
            home_xg = xg_val
        elif team_id == away_id:
            away_xg = xg_val
    return home_xg, away_xg


def _normalize_api_sports_result(raw: Dict[str, Any], league_code: str) -> Optional[Dict[str, Any]]:
    fm = raw.get("fixture") or {}
    home = (raw.get("teams") or {}).get("home") or {}
    away = (raw.get("teams") or {}).get("away") or {}
    if not fm or not home or not away:
        return None
    status_short = str(((fm.get("status") or {}).get("short")) or "").upper()
    if status_short not in _API_SPORTS_FINISHED:
        return None
    goals = raw.get("goals") or {}
    gh, ga = goals.get("home"), goals.get("away")
    if gh is None or ga is None:
        return None
    try:
        score_home, score_away = int(gh), int(ga)
    except (TypeError, ValueError):
        return None
    lg = raw.get("league") if isinstance(raw.get("league"), dict) else {}
    comp_meta: Dict[str, Any] = {}
    if (lg.get("name") or "").strip():
        comp_meta["api_league_name"] = str(lg.get("name")).strip()
    if (lg.get("round") or "").strip():
        comp_meta["api_round"] = str(lg.get("round")).strip()
    fb_name = LEAGUES.get(league_code, {}).get("name", league_code)
    title = display_competition_title(
        fallback_name=fb_name,
        api_league_name=comp_meta.get("api_league_name"),
        api_round=comp_meta.get("api_round"),
    )
    xg_home, xg_away = _xg_from_api_sports_row(raw)
    embedded_events = raw.get("events")
    row: Dict[str, Any] = {
        "id": fm.get("id"),
        "home": home.get("name", "?"),
        "away": away.get("name", "?"),
        "date": fm.get("date"),
        "league": league_code,
        "league_name": title,
        "score_home": score_home,
        "score_away": score_away,
        "scoreline": f"{score_home}–{score_away}",
        "status": status_short,
        "xg_home": xg_home,
        "xg_away": xg_away,
        "has_xg": xg_home is not None and xg_away is not None,
        "competition_meta": comp_meta,
    }
    if isinstance(embedded_events, list) and embedded_events:
        row["events"] = embedded_events
    return row


def _normalize_fdo_result(match: Dict[str, Any], league_code: str) -> Optional[Dict[str, Any]]:
    if not match:
        return None
    status = str(match.get("status") or "").upper()
    if status not in _FDO_FINISHED:
        return None
    home = match.get("homeTeam") or {}
    away = match.get("awayTeam") or {}
    date_s = match.get("utcDate")
    if not date_s or not home or not away:
        return None
    score = match.get("score") or {}
    ft = score.get("fullTime") or {}
    gh, ga = ft.get("home"), ft.get("away")
    if gh is None or ga is None:
        return None
    try:
        score_home, score_away = int(gh), int(ga)
    except (TypeError, ValueError):
        return None
    comp = match.get("competition") if isinstance(match.get("competition"), dict) else {}
    comp_meta: Dict[str, Any] = {}
    if (comp.get("name") or "").strip():
        comp_meta["fdo_competition_name"] = str(comp.get("name")).strip()
    fb_name = LEAGUES.get(league_code, {}).get("name", league_code)
    title = display_competition_title(
        fallback_name=fb_name,
        fdo_competition_name=comp_meta.get("fdo_competition_name"),
    )
    return {
        "id": match.get("id"),
        "home": home.get("name", "?"),
        "away": away.get("name", "?"),
        "date": date_s,
        "league": league_code,
        "league_name": title,
        "score_home": score_home,
        "score_away": score_away,
        "scoreline": f"{score_home}–{score_away}",
        "status": "FT",
        "xg_home": None,
        "xg_away": None,
        "has_xg": False,
        "competition_meta": comp_meta,
    }


def _result_key(row: Dict[str, Any]) -> str:
    return f"{row.get('home')}|{row.get('away')}|{row.get('date', '')}"


def _in_results_window(row: Dict[str, Any], window_start: datetime, window_end: datetime) -> bool:
    dt = parse_kickoff_utc(row.get("date"))
    if not dt:
        return False
    return window_start <= dt <= window_end


def fetch_league_recent_results(
    league_code: str,
    aggregator: Any,
    *,
    cache: Optional[Cache] = None,
) -> List[Dict[str, Any]]:
    """Finished fixtures for one league in the results lookback window (disk-cached)."""
    cache = cache or Cache()
    ttl = _cache_ttl_hours(1.0)
    cache_key = _league_results_cache_key(league_code)
    cached = cache.get(cache_key, ttl_hours=ttl)
    if isinstance(cached, list):
        return cached

    league = LEAGUES.get(league_code, {})
    now = datetime.now(timezone.utc)
    window_start, window_end = results_window_utc(now)
    date_from = window_start.strftime("%Y-%m-%d")
    date_to = window_end.strftime("%Y-%m-%d")
    from hibs_predictor.scrape_first import fixture_fetch_flags

    prefer_fdo, skip_as = fixture_fetch_flags()
    fetched: Dict[str, Dict[str, Any]] = {}
    fdo_comp = league.get("football_data_org_id")
    season_candidates = _fixture_fetch_season_candidates(
        fdo_comp, date_from, date_to, now, league_code=league_code
    )
    league_api_id = league.get("api_sports_id")

    def add(row: Optional[Dict[str, Any]]) -> None:
        if not row:
            return
        if not _in_results_window(row, window_start, window_end):
            return
        key = _result_key(row)
        if key not in fetched:
            fetched[key] = row

    def try_api_sports() -> None:
        if skip_as or "api_sports" not in aggregator.clients or not league_api_id:
            return
        try:
            for season in season_candidates:
                raw = aggregator.clients["api_sports"].fetch_fixtures_by_league(
                    int(league_api_id),
                    int(season),
                    date_from=date_from,
                    date_to=date_to,
                )
                for item in raw or []:
                    add(_normalize_api_sports_result(item, league_code))
                if fetched:
                    break
        except Exception as exc:
            print(f"[Results API-Sports] {league_code}: {exc!r}")

    def try_football_data() -> None:
        if "football_data_org" not in aggregator.clients:
            return
        from hibs_predictor.api_clients import football_data_requests_allowed

        if not football_data_requests_allowed():
            return
        comp = league.get("football_data_org_id")
        if not comp:
            return
        for season in season_candidates:
            try:
                raw = aggregator.clients["football_data_org"].fetch_fixtures(
                    comp,
                    season,
                    status=None,
                    date_from=date_from,
                    date_to=date_to,
                )
                for match in raw or []:
                    add(_normalize_fdo_result(match, league_code))
                if fetched:
                    break
            except Exception as exc:
                print(f"[Results Football-Data] {league_code} {comp} season={season}: {exc!r}")

    api_first = league_code in _API_FIRST_FIXTURE_LEAGUES
    if api_first or not prefer_fdo:
        try_api_sports()
        if not fetched:
            try_football_data()
    else:
        try_football_data()
        if not fetched:
            try_api_sports()

    def try_fotmob_results() -> None:
        if os.getenv("HIBS_ENABLE_FOTMOB_FIXTURES", "1").strip().lower() in ("0", "false", "no", "off"):
            return
        try:
            from hibs_predictor.scrapers import fotmob_client
            from hibs_predictor.scrapers.fotmob_client import fotmob_match_to_recent_format

            day = window_start.date()
            end_day = window_end.date()
            while day <= end_day:
                for m in fotmob_client.fixtures_for_league(league_code, day, day, cache=cache) or []:
                    norm = fotmob_match_to_recent_format(m)
                    if not norm:
                        continue
                    norm = dict(norm)
                    norm["league"] = league_code
                    add(norm)
                day = day + timedelta(days=1)
        except Exception as exc:
            print(f"[Results FotMob] {league_code}: {exc!r}")

    if not fetched:
        try_fotmob_results()

    rows = list(fetched.values())
    rows.sort(key=lambda r: r.get("date") or "", reverse=True)
    cache.set(cache_key, rows, ttl_hours=ttl)
    return rows


def _results_days_groups(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_day: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        day = row.get("kickoff_day_local") or ""
        if not day:
            continue
        by_day.setdefault(day, []).append(row)
    order_index = {c: i for i, c in enumerate(effective_dashboard_league_order())}
    out: List[Dict[str, Any]] = []
    for day_iso in sorted(by_day.keys(), reverse=True):
        day_rows = by_day[day_iso]
        by_league: Dict[str, List[Dict[str, Any]]] = {}
        for row in day_rows:
            lc = str(row.get("league") or "")
            by_league.setdefault(lc, []).append(row)
        leagues_out: List[Dict[str, Any]] = []
        for lc in sorted(by_league.keys(), key=lambda c: order_index.get(c, 999)):
            fixtures = by_league[lc]
            fixtures.sort(key=lambda r: r.get("kickoff_sort") or r.get("date") or "", reverse=True)
            name = fixtures[0].get("league_name") if fixtures else LEAGUES.get(lc, {}).get("name", lc)
            leagues_out.append({"code": lc, "name": name, "fixtures": fixtures})
        out.append(
            {
                "date_iso": day_iso,
                "heading": day_heading_for_local_date(day_iso, len(day_rows)).replace(
                    "fixtures", "results"
                ),
                "leagues": leagues_out,
            }
        )
    return out


def finalize_results_bundle(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    enriched = [attach_kickoff_display(dict(r)) for r in rows]
    for row in enriched:
        row["dashboard_region"] = league_dashboard_region(str(row.get("league") or ""))
    enriched.sort(key=lambda r: r.get("kickoff_sort") or r.get("date") or "", reverse=True)
    return {
        "all": enriched,
        "days": _results_days_groups(enriched),
        "total": len(enriched),
        "results_days": results_days(),
    }


def fetch_recent_results(
    aggregator: Any,
    *,
    cache: Optional[Cache] = None,
    include_domestic: bool = False,
) -> Dict[str, Any]:
    """Batched, cached fetch of finished fixtures for loaded/focus leagues."""
    cache = cache or Cache()
    ttl = _cache_ttl_hours(1.0)
    ck = _results_cache_key(include_domestic=include_domestic)
    cached = cache.get(ck, ttl_hours=ttl)
    if isinstance(cached, dict) and isinstance(cached.get("all"), list):
        bundle = dict(cached)
        bundle["results_days"] = results_days()
        return bundle

    codes = list(league_codes_for_fetch(include_domestic=include_domestic))
    workers = min(max(1, int(os.getenv("HIBS_FIXTURE_FETCH_WORKERS", "4") or 4)), len(codes) or 1)
    combined: Dict[str, Dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(fetch_league_recent_results, code, aggregator, cache=cache): code
            for code in codes
        }
        for fut in as_completed(futures):
            code = futures[fut]
            try:
                for row in fut.result():
                    key = _result_key(row)
                    prev = combined.get(key)
                    if not prev or (row.get("has_xg") and not prev.get("has_xg")):
                        combined[key] = row
            except Exception as exc:
                print(f"[Recent results] {code}: {exc!r}")

    bundle = finalize_results_bundle(list(combined.values()))
    if bundle.get("all"):
        _enrich_goal_scorers(bundle["all"], aggregator, cache)
        bundle = finalize_results_bundle(bundle["all"])
    if bundle.get("total"):
        cache.set(ck, bundle, ttl_hours=ttl)
    return bundle
