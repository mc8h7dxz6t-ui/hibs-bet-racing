"""Flask web dashboard for hibs-bet."""

import hashlib
import os
import sys
import threading
import time as _time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone, date
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(BASE_DIR, "src"))

from dotenv import load_dotenv

load_dotenv(os.path.join(BASE_DIR, ".env"))
load_dotenv(os.path.join(BASE_DIR, ".env.local"))

from hibs_predictor.app_logging import configure_app_logging, get_logger

_log_path = configure_app_logging(BASE_DIR)
log = get_logger("web")
if _log_path:
    log.info("Log file: %s", _log_path)

try:
    from hibs_predictor.m5_optimization import setup_optimizations

    _optimization_config = setup_optimizations()
    if _optimization_config["platform"]["is_apple_silicon"]:
        print("Apple Silicon (M-series) optimizations enabled")
except Exception as exc:
    print(f"M5 optimizations skipped: {exc}")

from flask import Flask, render_template, jsonify, request, abort, g, has_request_context, make_response, redirect, url_for, Response
from hibs_predictor.auth import (
    auth_enabled,
    check_password,
    init_app as init_auth,
    is_logged_in,
    login_required,
    login_user,
    logout_user,
    safe_next_url,
)
from hibs_predictor.config import (
    LEAGUES,
    LEAGUE_REGIONS,
    DASHBOARD_FILTER_REGIONS,
    league_dashboard_region,
)
from hibs_predictor.cache import Cache
from hibs_predictor.data_aggregator import DataAggregator
from hibs_predictor.betting_engine import (
    BettingEngine,
    OddsAnalyzer,
    TeamStrengthCalculator,
    prediction_unavailable_payload,
)
from hibs_predictor.health_probe import gather_health
from hibs_predictor.display_tz import display_tz_label, fixture_window_start_utc, fixture_window_end_utc
from hibs_predictor.fixture_utils import (
    cup_round_label,
    display_competition_title,
    fixture_status_short,
    fixture_team_name,
    format_goal_scorers_line,
    is_cup_competition,
    is_finished_fixture,
    normalize_fixture_display,
    normalize_position_dict,
    normalize_position_rank,
    position_points,
    position_rank,
    table_form_inconsistent,
    table_team_display,
)
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")

app = Flask(__name__, template_folder=TEMPLATE_DIR, static_folder=STATIC_DIR)
app.config["JSON_SORT_KEYS"] = False
init_auth(app)
try:
    from hibs_predictor.fve_lines_proxy import register_fve_lines_routes

    register_fve_lines_routes(app)
except Exception as _fve_reg_exc:
    log.warning("FVE lines proxy not registered: %s", _fve_reg_exc)
try:
    from hibs_predictor.institutional_readiness import log_startup_readiness, validate_production_config

    if (os.getenv("HIBS_PRODUCTION") or "").strip().lower() in ("1", "true", "yes", "on"):
        validate_production_config(strict=True)
    log_startup_readiness()
except RuntimeError:
    raise
except Exception:
    pass


@app.template_filter("table_team_label")
def _jinja_table_team_label(value: Any) -> str:
    label = table_team_display(value)
    return label or "—"


@app.template_filter("position_rank")
def _jinja_position_rank(value: Any) -> str:
    if isinstance(value, dict):
        rank = position_rank(value)
        return str(rank) if rank is not None else ""
    rank = normalize_position_rank(value)
    return str(rank) if rank is not None else str(value or "")


@app.after_request
def _persist_fetch_days_cookie(response):
    response = _set_fetch_days_cookie_if_requested(response)
    if request.path.startswith("/static/") and response.status_code == 200:
        response.headers.setdefault("Cache-Control", "public, max-age=86400")
    return response


aggregator = DataAggregator()
betting_engine = BettingEngine(aggregator.get_all_clients())

_health_cache: Dict[str, Any] = {"t": 0.0, "payload": None}
_HEALTH_TTL_SEC = 90.0
_cache_prune_last: float = 0.0
_CACHE_PRUNE_INTERVAL_SEC = 300.0
_dashboard_page_cache: Dict[str, Any] = {"t": 0.0, "etag": "", "body": None, "fetch_days": None}
_DASHBOARD_PAGE_TTL_SEC = 30.0
_DASHBOARD_PAGE_STALE_MAX_SEC = 3600.0
_dashboard_refresh_lock = __import__("threading").Lock()
_dashboard_refresh_inflight = False
_BUNDLE_DISK_KEYS = frozenset(
    {"all", "by_region", "by_league", "dashboard_days", "value_bets", "total", "fixture_coverage"}
)


def _api_football_season_year(now: datetime) -> int:
    """API-Football season id (Jul-based default; respects HIBS_CURRENT_SEASON)."""
    from hibs_predictor.season import api_football_season_year

    return api_football_season_year(now)


_FDO_CALENDAR_COMPS = frozenset({"WC", "EC", "UNL", "CL", "EL", "UECL"})
# UEFA club cups: API-Football season id is Jul-based; FDO often 403/429 on finals week.
_API_FIRST_FIXTURE_LEAGUES = frozenset({"UCL", "EUROPA_LEAGUE", "UECL", "INTL_FRIENDLIES"})
_FIXTURE_CACHE_VERSION = "v50"
_EMPTY_FIXTURE_CACHE_TTL_HOURS = 0.2  # short negative cache — avoid hour-long empty poison


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
    """Season years to try for fixtures. Domestic leagues use Jul-based season id; WC/EC/UNL also use calendar years in the fetch window."""
    from hibs_predictor.season import CALENDAR_YEAR_LEAGUES

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
    # Jul-based API season (e.g. 2025 for 2025–26) before calendar years in the window.
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


def _env_truthy(name: str) -> bool:
    return (os.getenv(name) or "").strip().lower() in ("1", "true", "yes", "on")


def _dashboard_league_order(*, include_domestic: bool = False) -> List[str]:
    from hibs_predictor.tournament_focus import effective_dashboard_league_order

    return effective_dashboard_league_order(include_domestic=include_domestic)


def _league_codes_for_fetch(*, include_domestic: bool = False) -> List[str]:
    from hibs_predictor.tournament_focus import (
        INTL_FRIENDLIES_CODE,
        friendlies_window_active,
        league_codes_for_fetch,
    )

    codes = league_codes_for_fetch(include_domestic=include_domestic)
    if friendlies_window_active() and INTL_FRIENDLIES_CODE in codes:
        codes = [INTL_FRIENDLIES_CODE] + [c for c in codes if c != INTL_FRIENDLIES_CODE]
    return codes


def _tournament_focus_context(*, include_domestic: bool = False) -> Dict[str, Any]:
    from hibs_predictor.tournament_focus import tournament_focus_context

    return tournament_focus_context(include_domestic=include_domestic)


def _show_players_dock() -> bool:
    """Permanent players snapshot in the right dock (set HIBS_SHOW_PLAYERS_DOCK=0 to hide)."""
    return (os.getenv("HIBS_SHOW_PLAYERS_DOCK") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _launch_media_enabled() -> bool:
    """Optional muted launch-wait.mp4 on dashboard overlay (HIBS_LAUNCH_MEDIA=1)."""
    return (os.getenv("HIBS_LAUNCH_MEDIA") or "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _players_dock_context(*, include_domestic: bool = False) -> Dict[str, Any]:
    """Right-rail players snapshot from cached fixture bundle (no blocking fetch)."""
    show = _show_players_dock()
    groups: List[Dict[str, Any]] = []
    cold = False
    if show:
        disk = Cache().peek(_all_fixtures_cache_key(include_domestic=include_domestic))
        if isinstance(disk, dict) and disk.get("all"):
            groups = _players_groups_for_ui_data(disk, limit=12, include_domestic=include_domestic)
        elif isinstance(disk, dict) and (disk.get("cold_start") or disk.get("cache_stale")):
            cold = True
        elif disk is None:
            cold = True
    return {
        "show_players_dock": show,
        "players_dock_groups": groups,
        "players_dock_cold_start": cold,
    }


@app.context_processor
def inject_hibs_shell():
    from hibs_predictor.hibs_brand import hibs_brand_context
    from hibs_predictor.product_links import infer_football_nav_active, infer_product_active, product_bar_context
    from hibs_predictor.scrape_first import scrape_first_status

    include_domestic = request.args.get("domestic") == "1"
    ctx = _players_dock_context(include_domestic=include_domestic)
    ctx["scrape_first_status"] = scrape_first_status()
    ctx["launch_media_enabled"] = _launch_media_enabled()
    ctx["hibs_auth_enabled"] = auth_enabled()
    ctx["hibs_logged_in"] = is_logged_in()
    ctx.update(hibs_brand_context())
    path = getattr(request, "path", "/") or "/"
    ctx.update(product_bar_context(active=infer_product_active(path)))
    ctx["football_nav_active"] = infer_football_nav_active(path)
    ctx["portfolio_api_url"] = os.environ.get(
        "HIBS_PORTFOLIO_API_URL", "http://127.0.0.1:5003/api/portfolio/summary"
    )
    racing_base = os.environ.get("HIBS_RACING_BASE_URL", "http://127.0.0.1:5003").rstrip("/")
    ctx["hibs_racing_base_url"] = racing_base
    if "hibs_trading_status_url" not in ctx:
        ctx["hibs_trading_status_url"] = os.environ.get(
            "HIBS_TRADING_STATUS_URL", "/harvested-execution"
        )
    if "trading_metrics_url" not in ctx:
        ctx["trading_metrics_url"] = os.environ.get(
            "TRADING_METRICS_URL", "http://127.0.0.1:9109"
        )
    if "portfolio_racing_url" not in ctx:
        ctx["portfolio_racing_url"] = racing_base + "/portfolio"
    if "portfolio_football_url" not in ctx:
        ctx["portfolio_football_url"] = "/tracker"
    try:
        from hibs_predictor.affiliate_config import public_affiliate_context

        ctx.update(public_affiliate_context())
    except Exception:
        ctx.update(
            {
                "affiliate_enabled": False,
                "affiliate_bookmakers": [],
                "affiliate_default_bookmaker": None,
                "affiliate_revenue_share_enabled": False,
                "affiliate_master_revenue_share_pct": 20,
            }
        )
    return ctx


def _fixture_key(fixture: Dict[str, Any]) -> str:
    from hibs_predictor.fixture_utils import fixture_team_name

    home = fixture_team_name(fixture, "home")
    away = fixture_team_name(fixture, "away")
    return f"{home}|{away}|{fixture.get('date', '')}"


_ALLOWED_FETCH_DAYS = (5, 7)
_FETCH_DAYS_COOKIE = "hibs_fetch_days"
_FETCH_DAYS_DEFAULT = 5


def _normalize_fetch_days(raw: Any, *, default: int = _FETCH_DAYS_DEFAULT) -> int:
    """User-selectable fixture window: only 5 or 7 days."""
    try:
        d = int(raw)
    except (TypeError, ValueError):
        return default
    return d if d in _ALLOWED_FETCH_DAYS else default


def _fetch_days_from_env() -> int:
    return _normalize_fetch_days(os.getenv("HIBS_FETCH_DAYS", str(_FETCH_DAYS_DEFAULT)))


def _fixture_window_days_for_league(league_code: str) -> int:
    """Friendlies: wider horizon; LOI/Nordics and others: dashboard window only (5 or 7 days)."""
    from hibs_predictor.tournament_focus import (
        INTL_FRIENDLIES_CODE,
        friendlies_fetch_window_days,
        friendlies_window_active,
        summer_daily_league_codes,
    )

    days = _fetch_window_days()
    code = (league_code or "").strip().upper()
    if code in summer_daily_league_codes():
        return days
    if code != INTL_FRIENDLIES_CODE:
        return days
    if not friendlies_window_active():
        return days
    return friendlies_fetch_window_days(dashboard_days=days)


def _fetch_window_days() -> int:
    """Resolve fixture window for this request (query ?days=, cookie, env) or scripts (env only)."""
    cached = getattr(g, "fetch_window_days", None) if has_request_context() else None
    if cached is not None:
        return int(cached)

    resolved = _fetch_days_from_env()
    if has_request_context():
        if request.args.get("days") is not None:
            resolved = _normalize_fetch_days(request.args.get("days"), default=resolved)
        elif request.cookies.get(_FETCH_DAYS_COOKIE):
            resolved = _normalize_fetch_days(
                request.cookies.get(_FETCH_DAYS_COOKIE), default=resolved
            )
        g.fetch_window_days = resolved
    return resolved


def _set_fetch_days_cookie_if_requested(response):
    """Persist ?days=5|7 on the dashboard response so API refreshes keep the window."""
    if not has_request_context():
        return response
    raw = request.args.get("days")
    if raw is None:
        return response
    days = _normalize_fetch_days(raw, default=_fetch_window_days())
    response.set_cookie(
        _FETCH_DAYS_COOKIE,
        str(days),
        max_age=60 * 60 * 24 * 365,
        samesite="Lax",
        path="/",
    )
    return response


def _min_league_chip_fixtures() -> int:
    """Leagues with fewer upcoming fixtures in the window are hidden from filter chips (still in All)."""
    try:
        n = int(os.getenv("HIBS_MIN_LEAGUE_CHIP_FIXTURES", "1"))
    except ValueError:
        n = 1
    return max(1, min(20, n))


def _ui_data_quality_min_pct() -> int:
    try:
        return max(50, min(100, int(os.getenv("HIBS_UI_FULL_DATA_MIN_PCT", "85"))))
    except ValueError:
        return 85


def _ui_show_dq90_chip() -> bool:
    return (os.getenv("HIBS_UI_SHOW_DQ90_CHIP") or "1").strip().lower() not in ("0", "false", "no", "off")


def _all_fixtures_cache_key(*, include_domestic: bool = False) -> str:
    from hibs_predictor.tournament_focus import tournament_focus_active

    if tournament_focus_active():
        focus = "full" if include_domestic else "intl"
    else:
        focus = "all"
    return f"all_fixtures_{_fetch_window_days()}d_{focus}_{_FIXTURE_CACHE_VERSION}"


def _hibs_debug_log(message: str) -> None:
    if _env_truthy("HIBS_DEBUG"):
        print(f"[HIBS_DEBUG] {message}")


def _log_resilience(event: str, **fields: object) -> None:
    from hibs_predictor.app_logging import get_logger, log_resilience_event

    log_resilience_event(get_logger("resilience"), event, **fields)


def _cache_ttl_hours(default: float = 1.0) -> float:
    try:
        base = max(0.01, float(os.getenv("HIBS_CACHE_TTL_HOURS", str(default))))
    except ValueError:
        base = default
    try:
        from hibs_predictor.tournament_focus import domestic_offseason_active

        if domestic_offseason_active():
            summer_raw = (os.getenv("HIBS_CACHE_TTL_SUMMER_HOURS") or "").strip()
            if summer_raw:
                return max(base, float(summer_raw))
            return max(base, 4.0)
    except Exception:
        pass
    return base


def _provider_guard_blocked(service: str = "api_sports") -> bool:
    """True when the local rate-limit guard would block outbound API calls."""
    try:
        from hibs_predictor.rate_limiter import RateLimiter

        return RateLimiter().block_reason(service) is not None
    except Exception:
        return False


def _stale_league_fixture_rows(cache: Cache, cache_key: str) -> List[Dict[str, Any]]:
    """Disk league bundle ignoring TTL (post-deploy / guard-blocked warm)."""
    peeked = cache.peek(cache_key)
    return peeked if isinstance(peeked, list) else []


def _stale_fixture_row_index(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {_fixture_key(row): row for row in rows if isinstance(row, dict) and _fixture_key(row)}


def _merge_stale_fixture_row(row: Dict[str, Any], stale: Optional[Dict[str, Any]]) -> None:
    """Keep richer enrichment and never downgrade an existing DQ score after partial enrich."""
    if not stale:
        return
    stale_dq = stale.get("data_quality") if isinstance(stale.get("data_quality"), dict) else {}
    new_dq = row.get("data_quality") if isinstance(row.get("data_quality"), dict) else {}
    try:
        stale_pct = float(stale_dq.get("score_pct")) if stale_dq.get("score_pct") is not None else None
    except (TypeError, ValueError):
        stale_pct = None
    try:
        new_pct = float(new_dq.get("score_pct")) if new_dq.get("score_pct") is not None else None
    except (TypeError, ValueError):
        new_pct = None
    if stale_pct is not None and (new_pct is None or stale_pct > new_pct):
        row["data_quality"] = dict(stale_dq)
    stale_fresh = _slim_row_enrich_fresh(stale)
    new_fresh = _slim_row_enrich_fresh(row)
    if stale_fresh and not new_fresh:
        for key in (
            "home_stats",
            "away_stats",
            "home_recent_n",
            "away_recent_n",
            "home_last10",
            "away_last10",
            "home_position",
            "away_position",
            "all_bookmaker_odds",
            "best_odds_1x2",
            "best_odds_source",
            "fixture_injuries",
            "market_odds",
            "team_news_meta",
            "fixture_lineups",
            "lineup_meta",
            "xg_home",
            "xg_away",
            "xg_source",
            "xg_source_label",
            "xg_confidence_tier",
            "xg_source_hint",
            "scraped_xg_meta",
            "supplemental",
            "enriched_at",
        ):
            stale_val = stale.get(key)
            if stale_val in (None, "", [], {}):
                continue
            row[key] = stale_val
        if stale_pct is not None and (new_pct is None or stale_pct > new_pct):
            row["data_quality"] = dict(stale_dq)


def _preserve_data_quality_max(row: Dict[str, Any], new_dq: Dict[str, Any]) -> None:
    """Apply new DQ only when it improves score_pct — never cliff after merge/rerun."""
    existing = row.get("data_quality") if isinstance(row.get("data_quality"), dict) else {}
    try:
        old_pct = float(existing.get("score_pct")) if existing.get("score_pct") is not None else None
        new_pct = float(new_dq.get("score_pct") or 0)
    except (TypeError, ValueError):
        row["data_quality"] = dict(new_dq)
        return
    if old_pct is not None and old_pct > new_pct:
        return
    row["data_quality"] = dict(new_dq)


_TRANSIENT_PREDICTION_BLOCK_REASONS = frozenset({"api_rate_guard", "fixture_enrichment_failed"})


def _row_as_enriched_for_predict(row: Dict[str, Any]) -> Dict[str, Any]:
    """Build predict input from a dashboard row (post-merge), without stale block flags."""
    skip = {
        "prediction",
        "has_value_bet",
        "compact_xg_home",
        "compact_xg_away",
        "dashboard_region",
        "pick_menu",
        "structured_insight",
    }
    enriched = {k: v for k, v in row.items() if k not in skip}
    enriched.pop("_hibs_prediction_blocked", None)
    enriched.pop("_hibs_prediction_block_reason", None)
    dq = row.get("data_quality")
    if isinstance(dq, dict):
        enriched["data_quality"] = dict(dq)
    best = row.get("best_odds_1x2") or {}
    if isinstance(best, dict):
        for side in ("home", "draw", "away"):
            if best.get(side) is not None:
                enriched[f"odds_{side}"] = best[side]
        try:
            enriched["odds_available"] = all(float(best.get(k) or 0) > 1.0 for k in ("home", "draw", "away"))
        except (TypeError, ValueError):
            enriched.setdefault("odds_available", False)
    return enriched


def _abstain_data_pct_floor() -> float:
    try:
        return float(os.getenv("HIBS_ABSTAIN_DATA_PCT", "48"))
    except ValueError:
        return 48.0


def _prediction_rerun_eligible(row: Dict[str, Any], reason: str) -> bool:
    if not _slim_row_enrich_fresh(row):
        return False
    if reason in _TRANSIENT_PREDICTION_BLOCK_REASONS:
        return True
    if reason == "data_coverage_too_thin":
        dq = row.get("data_quality") if isinstance(row.get("data_quality"), dict) else {}
        try:
            pct = float(dq.get("score_pct") or 0)
        except (TypeError, ValueError):
            return False
        return pct >= _abstain_data_pct_floor()
    return False


def _maybe_rerun_prediction_after_stale_merge(row: Dict[str, Any]) -> bool:
    pred = row.get("prediction")
    if not isinstance(pred, dict) or not pred.get("prediction_unavailable"):
        return False
    reason = str(pred.get("prediction_unavailable_reason") or "")
    if not _prediction_rerun_eligible(row, reason):
        return False
    enriched = _row_as_enriched_for_predict(row)
    try:
        new_pred = betting_engine.predict_with_confidence(enriched)
    except Exception as exc:
        print(f"[Prediction rerun] {row.get('home')} v {row.get('away')}: {exc!r}")
        return False
    if not isinstance(new_pred, dict) or new_pred.get("prediction_unavailable"):
        return False
    row["prediction"] = new_pred
    _preserve_data_quality_max(row, _data_quality_for_enriched(enriched, new_pred))
    row["has_value_bet"] = bool(
        new_pred.get("has_any_value")
        or new_pred.get("value_bets")
        or new_pred.get("value_bets_alt")
    )
    return True


def _repair_guard_blocked_predictions(fixtures: List[Dict[str, Any]]) -> int:
    n = 0
    for row in fixtures:
        if isinstance(row, dict) and _maybe_rerun_prediction_after_stale_merge(row):
            n += 1
    return n


def _merge_league_fixture_lists(
    new_rows: List[Dict[str, Any]], stale_rows: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Union league bundles by fixture key; never downgrade row enrichment or DQ."""
    stale_by_key = _stale_fixture_row_index(stale_rows)
    merged: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for row in new_rows:
        if not isinstance(row, dict):
            continue
        key = _fixture_key(row)
        if key:
            _merge_stale_fixture_row(row, stale_by_key.get(key))
            seen.add(key)
        merged.append(row)
    for key, stale in stale_by_key.items():
        if key not in seen:
            merged.append(stale)
    merged.sort(key=lambda x: x.get("date") or "")
    return merged


def _merge_stale_all_fixtures_rows(
    rows: List[Dict[str, Any]],
    stale_rows: List[Dict[str, Any]],
) -> None:
    """Merge richer per-fixture disk rows into a fresh bundle build (never downgrade DQ)."""
    stale_by_key = _stale_fixture_row_index(stale_rows)
    for row in rows:
        _merge_stale_fixture_row(row, stale_by_key.get(_fixture_key(row)))


def _bundle_enrich_fresh_count(bundle: Dict[str, Any]) -> int:
    return sum(1 for row in bundle.get("all") or [] if _slim_row_enrich_fresh(row))


def _fixture_bundle_fetch_lock_path() -> str:
    from hibs_predictor.cache import default_cache_dir

    return os.path.join(default_cache_dir(), ".fetch_all_fixtures.lock")


def _acquire_fixture_bundle_fetch_lock(*, blocking: bool):
    """Cross-worker mutex so two gunicorn workers do not double API enrich storms."""
    import fcntl

    os.makedirs(os.path.dirname(_fixture_bundle_fetch_lock_path()), exist_ok=True)
    handle = open(_fixture_bundle_fetch_lock_path(), "a+")
    flags = fcntl.LOCK_EX if blocking else fcntl.LOCK_EX | fcntl.LOCK_NB
    fcntl.flock(handle.fileno(), flags)
    return handle


def _release_fixture_bundle_fetch_lock(handle: Any) -> None:
    import fcntl

    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()


def _bundle_ok_to_persist(result: Dict[str, Any]) -> bool:
    rows = result.get("all") or []
    if not rows:
        return False
    if _all_fixtures_bundle_fresh(result):
        return True
    fresh = _bundle_enrich_fresh_count(result)
    return fresh >= max(1, len(rows) // 4)


def _maybe_prune_cache(cache: Cache) -> None:
    """Lightweight stale prune (throttled) when HIBS_CACHE_PRUNE is enabled."""
    global _cache_prune_last
    if (os.getenv("HIBS_CACHE_PRUNE") or "1").strip().lower() in ("0", "false", "no"):
        return
    import time as _time

    now = _time.monotonic()
    if now - _cache_prune_last < _CACHE_PRUNE_INTERVAL_SEC:
        return
    _cache_prune_last = now
    try:
        cache.prune_stale()
    except Exception:
        pass


def _clear_health_cache() -> None:
    _health_cache["t"] = 0.0
    _health_cache["payload"] = None


def _clear_dashboard_page_cache() -> None:
    _dashboard_page_cache["t"] = 0.0
    _dashboard_page_cache["etag"] = ""
    _dashboard_page_cache["body"] = None
    _dashboard_page_cache["fetch_days"] = None


def _is_complete_fixture_bundle(cached: Any) -> bool:
    """Disk bundle written by fetch_all_fixtures (not a legacy list-only payload)."""
    return isinstance(cached, dict) and bool(cached.get("all")) and _BUNDLE_DISK_KEYS.issubset(cached.keys())


def _dashboard_page_cache_get(*, allow_stale: bool = False) -> Optional[Tuple[bytes, str]]:
    now = _time.monotonic()
    body = _dashboard_page_cache.get("body")
    etag = _dashboard_page_cache.get("etag") or ""
    if body is None or not etag:
        return None
    age = now - float(_dashboard_page_cache.get("t") or 0)
    if age > _DASHBOARD_PAGE_TTL_SEC:
        if not allow_stale or age > _DASHBOARD_PAGE_STALE_MAX_SEC:
            return None
    if _dashboard_page_cache.get("fetch_days") != _fetch_window_days():
        return None
    from hibs_predictor.recent_results import results_days

    if _dashboard_page_cache.get("results_days") != results_days():
        return None
    return body, etag


def _schedule_dashboard_refresh() -> None:
    """Background rebuild so the next request gets a fresh page without blocking nginx."""
    global _dashboard_refresh_inflight
    if not _env_truthy("HIBS_WARM_FIXTURE_CACHE"):
        return
    with _dashboard_refresh_lock:
        if _dashboard_refresh_inflight:
            return
        _dashboard_refresh_inflight = True

    import threading

    def _run() -> None:
        global _dashboard_refresh_inflight
        try:
            fetch_all_fixtures(
                attach_live=False,
                include_domestic=False,
                allow_stale=True,
                force_refresh=False,
                reboost=True,
            )
            _clear_dashboard_page_cache()
        except Exception as exc:
            print(f"[Dashboard refresh] {exc!r}")
        finally:
            with _dashboard_refresh_lock:
                _dashboard_refresh_inflight = False

    threading.Thread(target=_run, name="hibs-dashboard-refresh", daemon=True).start()


def _dashboard_page_cache_set(body: bytes) -> str:
    etag = hashlib.md5(body, usedforsecurity=False).hexdigest()[:16]
    _dashboard_page_cache["t"] = _time.monotonic()
    _dashboard_page_cache["etag"] = etag
    _dashboard_page_cache["body"] = body
    _dashboard_page_cache["fetch_days"] = _fetch_window_days()
    from hibs_predictor.recent_results import results_days

    _dashboard_page_cache["results_days"] = results_days()
    return etag


def _dashboard_lite_mode() -> bool:
    """Lighter first paint: skip assistant bundle build; fewer parallel league fetches."""
    return _env_truthy("HIBS_DASHBOARD_LITE")


def _progressive_load_enabled() -> bool:
    """Serve HTML from cache/stale fixtures first; load insights, results, assistant after paint."""
    raw = os.getenv("HIBS_PROGRESSIVE_LOAD", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _defer_assistant_on_page() -> bool:
    """Skip embedding assistant JSON in HTML; client loads /api/assistant/snapshot after paint."""
    return _progressive_load_enabled() or _dashboard_lite_mode()


def _insights_content_context(
    data: Dict[str, Any],
    insights: Dict[str, Any],
) -> Dict[str, Any]:
    """Template context shared by /insights and /api/insights/content."""
    fixture_coverage = data.get("fixture_coverage") or {}
    return {
        "insights": insights,
        "total": data.get("total", 0),
        "value_bet_count": data.get("value_bet_count", 0),
        "fetch_days": _fetch_window_days(),
        "data_quality_ui_min": _ui_data_quality_min_pct(),
        "dashboard_info": _dashboard_info_box(fixture_coverage, data.get("total", 0)),
        "fixture_coverage": fixture_coverage,
        "display_tz_label": display_tz_label(),
    }


def _fixture_fetch_workers() -> int:
    if _dashboard_lite_mode():
        default = "3"
    else:
        default = "4" if _env_truthy("HIBS_MAX_DATA") else "6"
    try:
        n = int(os.getenv("HIBS_FIXTURE_FETCH_WORKERS", default))
    except ValueError:
        n = int(default)
    return max(1, min(12, n))


def _maybe_warm_fixture_cache() -> None:
    """Background warm of all_fixtures disk cache (production cold start)."""
    if not _env_truthy("HIBS_WARM_FIXTURE_CACHE"):
        return
    _schedule_dashboard_refresh()


def _load_fixtures_for_http(
    *,
    attach_live: bool = False,
    include_domestic: bool = False,
) -> Dict[str, Any]:
    """Request-path fixture load: cached, stale, or cold shell — never block on cold rebuild."""
    ck = _all_fixtures_cache_key(include_domestic=include_domestic)
    cache = Cache()
    ttl = _cache_ttl_hours(1.0)
    cached = cache.get(ck, ttl_hours=ttl)
    if cached and _is_complete_fixture_bundle(cached):
        bundle = dict(cached)
        bundle["fetch_days"] = _fetch_window_days()
        if not _all_fixtures_bundle_fresh(cached):
            bundle["cache_stale"] = True
        n_repaired = _repair_guard_blocked_predictions(bundle.get("all") or [])
        if n_repaired:
            log.info("Repaired %d guard-blocked prediction(s) in cached bundle", n_repaired)
        if attach_live:
            _refresh_live_on_bundle(bundle)
        return bundle

    stale = _stale_fixture_bundle_for_refresh(include_domestic=include_domestic)
    if stale:
        n_repaired = _repair_guard_blocked_predictions(stale.get("all") or [])
        if n_repaired:
            log.info("Repaired %d guard-blocked prediction(s) in stale bundle", n_repaired)
        if attach_live:
            _refresh_live_on_bundle(stale)
        _schedule_dashboard_refresh()
        return stale

    _schedule_dashboard_refresh()
    return _cold_fixture_bundle(include_domestic=include_domestic)


def _slim_row_enrich_fresh(row: Dict[str, Any]) -> bool:
    """True when a cached per-league row has core API blocks (stats + form); xG tier may still upgrade later."""
    from hibs_predictor.data_quality import _has_stats

    home_id = row.get("home_id")
    away_id = row.get("away_id")

    def _recent_ok(side: str) -> bool:
        try:
            n = int(row.get(f"{side}_recent_n") or 0)
        except (TypeError, ValueError):
            n = 0
        if n >= 5:
            return True
        last = row.get(f"{side}_last10") or []
        return len(last) >= 5

    if home_id and not _recent_ok("home"):
        return False
    if away_id and not _recent_ok("away"):
        return False
    if home_id and not _has_stats(row.get("home_stats")):
        return False
    if away_id and not _has_stats(row.get("away_stats")):
        return False
    return True


def _league_fixture_cache_fresh(rows: List[Dict[str, Any]]) -> bool:
    """False when any row in a per-league disk cache needs another enrich pass."""
    if not rows:
        return False
    return all(_slim_row_enrich_fresh(row) for row in rows)


def _league_codes_enrich_priority_order(codes: List[str]) -> List[str]:
    """Summer/offseason: Nordics ahead; optional today-first when HIBS_ENRICH_PRIORITY_TODAY=1."""
    from hibs_predictor.deep_enrich import league_codes_priority_today, league_codes_priority_xg_gaps
    from hibs_predictor.tournament_focus import domestic_offseason_active

    ordered = league_codes_priority_xg_gaps(list(codes)) if domestic_offseason_active() else list(codes)
    if not _env_truthy("HIBS_ENRICH_PRIORITY_TODAY"):
        return ordered
    from hibs_predictor.deep_enrich import fixture_is_today, league_codes_priority_today

    days = _fetch_window_days()
    prefer_fdo = _env_truthy("HIBS_PREFER_FOOTBALL_DATA_FIXTURES")
    skip_as_fx = _env_truthy("HIBS_SKIP_API_SPORTS_FIXTURES")
    cache = Cache()
    preview: Dict[str, List[Dict[str, Any]]] = {}
    for code in ordered:
        cache_key = f"fixtures_{days}d_{code}_{_FIXTURE_CACHE_VERSION}_{int(prefer_fdo)}{int(skip_as_fx)}"
        cached = cache.get(cache_key, ttl_hours=_cache_ttl_hours(1.0)) or []
        preview[code] = cached if isinstance(cached, list) else []
    return league_codes_priority_today(ordered, preview)


def _fetch_all_league_fixtures_parallel(
    *, include_domestic: bool = False, allow_stale: bool = False
) -> List[Dict]:
    """Fetch per-league fixture rows concurrently (each league uses its own disk cache)."""
    from hibs_predictor.tournament_focus import INTL_FRIENDLIES_CODE, friendlies_window_active

    codes = _league_codes_enrich_priority_order(_league_codes_for_fetch(include_domestic=include_domestic))
    out: List[Dict] = []
    if friendlies_window_active() and INTL_FRIENDLIES_CODE in codes:
        try:
            out.extend(fetch_next_48h_fixtures(INTL_FRIENDLIES_CODE, allow_stale=allow_stale))
            print(f"[AllFixtures] priority {INTL_FRIENDLIES_CODE}: {len(out)} rows")
        except Exception as exc:
            print(f"[AllFixtures] priority {INTL_FRIENDLIES_CODE}: {exc!r}")
        codes = [c for c in codes if c != INTL_FRIENDLIES_CODE]
    if not codes:
        return out
    workers = min(_fixture_fetch_workers(), len(codes))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(fetch_next_48h_fixtures, code, allow_stale=allow_stale): code
            for code in codes
        }
        for fut in as_completed(futures):
            league_code = futures[fut]
            try:
                out.extend(fut.result())
            except Exception as e:
                print(f"[AllFixtures] {league_code}: {e}")
    return out


def _refresh_live_on_bundle(bundle: Dict[str, Any]) -> None:
    """Lightweight in-play merge for dashboard; avoids full re-finalize on disk cache hit."""
    from hibs_predictor.live_scores import attach_live_to_fixtures

    all_f = bundle.get("all") or []
    if not all_f:
        return
    try:
        attach_live_to_fixtures(all_f, aggregator, include_events=True, include_stats=True)
    except Exception as exc:
        print(f"[Live scores] refresh failed: {exc!r}")


def _live_snapshot_on_load_enabled() -> bool:
    return (os.getenv("HIBS_LIVE_SNAPSHOT_ON_LOAD") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _refresh_live_kickoff_window(fixtures: List[Dict[str, Any]]) -> None:
    """Attach live scores only for fixtures near kickoff (fast first paint)."""
    if not _live_snapshot_on_load_enabled() or not fixtures:
        return
    from hibs_predictor.live_scores import attach_live_to_fixtures, fixtures_in_kickoff_poll_window

    subset = fixtures_in_kickoff_poll_window(fixtures)
    if not subset:
        return
    stats_on_load = (os.getenv("HIBS_LIVE_ATTACH_STATS_ON_LOAD") or "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    try:
        attach_live_to_fixtures(
            subset,
            aggregator,
            include_events=True,
            include_stats=stats_on_load,
        )
    except Exception as exc:
        print(f"[Live kickoff window] refresh failed: {exc!r}")


def _all_fixtures_bundle_fresh(bundle: Dict[str, Any]) -> bool:
    """False when bundled rows are missing core form/stats (post-429 thin snapshots)."""
    return _league_fixture_cache_fresh(bundle.get("all") or [])


def _reset_provider_rate_limits() -> None:
    """Fixture cache clear should not leave API-Sports locally blocked (403/400 guard)."""
    try:
        from hibs_predictor.rate_limiter import RateLimiter

        RateLimiter().reset_all()
        print("[Cache clear] reset API rate-limit counters")
    except Exception as exc:
        print(f"[Cache clear] rate-limit reset failed: {exc!r}")


def clear_application_caches(*, all_disk: bool = False, reset_rate_limits: bool = True) -> int:
    """Clear in-memory health cache and on-disk fixture caches (or all JSON when all_disk)."""
    _clear_health_cache()
    _clear_dashboard_page_cache()
    clear_assistant_bundle_cache()
    if reset_rate_limits:
        _reset_provider_rate_limits()
    cache = Cache()
    if all_disk:
        return cache.clear_all()
    removed = 0
    for pattern in (
        "all_fixtures_",
        "fixtures_",
        "league_",
        "recent_results_",
        "results_",
        "enriched_fixture_",
    ):
        removed += cache.clear_pattern(pattern, prefix=True)
    return removed


def _safe_enrich(fixture: Dict[str, Any], league_code: str) -> Dict[str, Any]:
    """Prefer full enrichment; on failure list the fixture without inventing xG/form/odds (unless HIBS_ALLOW_DUMMY=1)."""
    if _provider_guard_blocked("api_sports") and not _env_truthy("HIBS_ALLOW_DUMMY"):
        out = dict(fixture)
        out.setdefault("home_recent", [])
        out.setdefault("away_recent", [])
        out.setdefault("home_stats", {})
        out.setdefault("away_stats", {})
        out.setdefault("home_position", {})
        out.setdefault("away_position", {})
        out.setdefault("odds_home", None)
        out.setdefault("odds_draw", None)
        out.setdefault("odds_away", None)
        out.setdefault("odds_available", False)
        out.setdefault("all_bookmaker_odds", [])
        out.setdefault("fixture_injuries", [])
        out.setdefault("market_odds", {})
        out["_hibs_prediction_blocked"] = True
        out["_hibs_prediction_block_reason"] = "api_rate_guard"
        return out
    try:
        return aggregator.enrich_fixture(fixture, league_code)
    except Exception as exc:
        print(f"[Enrich fallback] {league_code} {_fixture_key(fixture)}: {exc}")
        if _env_truthy("HIBS_ALLOW_DUMMY"):
            league = LEAGUES.get(league_code, {})
            out = dict(fixture)
            out.setdefault("home_recent", [])
            out.setdefault("away_recent", [])
            out.setdefault("home_stats", {})
            out.setdefault("away_stats", {})
            out.setdefault("home_form", 0.5)
            out.setdefault("away_form", 0.5)
            out.setdefault("home_home_factor", 1.0)
            out.setdefault("away_away_factor", 1.0)
            out.setdefault("home_position", {})
            out.setdefault("away_position", {})
            out.setdefault("xg_home", 1.25)
            out.setdefault("xg_away", 1.15)
            out.setdefault("odds_home", None)
            out.setdefault("odds_draw", None)
            out.setdefault("odds_away", None)
            out.setdefault("odds_available", False)
            out.setdefault("all_bookmaker_odds", [])
            out.setdefault("fixture_injuries", [])
            out.setdefault("market_odds", {})
            out.setdefault("odds_secondary", None)
            out.setdefault("odds_cross_max_implied_diff_pct", 0.0)
            out.setdefault("league_factor", league.get("strength_factor", 1.0))
            out.setdefault("xg_source", "goals_proxy")
            out.setdefault("data_quality", {"score_pct": 0.0, "blocks": [], "full_scope": False, "strong_scope": False})
            return out
        out = dict(fixture)
        out.setdefault("home_recent", [])
        out.setdefault("away_recent", [])
        out.setdefault("home_stats", {})
        out.setdefault("away_stats", {})
        out.setdefault("home_position", {})
        out.setdefault("away_position", {})
        out.setdefault("odds_home", None)
        out.setdefault("odds_draw", None)
        out.setdefault("odds_away", None)
        out.setdefault("odds_available", False)
        out.setdefault("all_bookmaker_odds", [])
        out.setdefault("fixture_injuries", [])
        out.setdefault("market_odds", {})
        out.setdefault("odds_secondary", None)
        out.setdefault("odds_cross_max_implied_diff_pct", 0.0)
        out.setdefault("data_quality", {"score_pct": 0.0, "blocks": [], "full_scope": False, "strong_scope": False})
        out["_hibs_prediction_blocked"] = True
        out["_hibs_prediction_block_reason"] = "fixture_enrichment_failed"
        # Enrichment can fail after form/stats work but before odds; odds bundle only needs fixture id + team names.
        try:
            bundle = aggregator._fetch_odds_bundle(out, league_code)
            if isinstance(bundle, dict):
                out["odds_home"] = bundle.get("odds_home")
                out["odds_draw"] = bundle.get("odds_draw")
                out["odds_away"] = bundle.get("odds_away")
                out["odds_available"] = bool(bundle.get("odds_available"))
                out["all_bookmaker_odds"] = bundle.get("all_bookmaker_odds") or []
                out["market_odds"] = bundle.get("market_odds") or {}
                out["odds_secondary"] = bundle.get("odds_secondary")
                out["odds_cross_max_implied_diff_pct"] = bundle.get("odds_cross_max_implied_diff_pct") or 0.0
                out["odds_primary_source"] = bundle.get("odds_primary_source")
        except Exception:
            pass
        return out


def _competition_meta_from_api_sports(raw: Dict[str, Any]) -> Dict[str, Any]:
    lg = raw.get("league")
    if not isinstance(lg, dict):
        return {}
    meta: Dict[str, Any] = {}
    name = (lg.get("name") or "").strip()
    rnd = (lg.get("round") or "").strip()
    if name:
        meta["api_league_name"] = name
    if rnd:
        meta["api_round"] = rnd
    return meta


def _fdo_round_from_match(match: Dict[str, Any]) -> Optional[str]:
    stage = match.get("stage")
    if stage is None or stage == "":
        return None
    s = str(stage).strip().upper().replace("-", "_")
    if s in ("REGULAR_SEASON", "GROUP_STAGE"):
        return None
    labels = {
        "FINAL": "Final",
        "SEMI_FINALS": "Semi-finals",
        "QUARTER_FINALS": "Quarter-finals",
        "LAST_16": "Round of 16",
        "LAST_32": "Round of 32",
        "ROUND_OF_16": "Round of 16",
        "PLAYOFF_ROUND": "Play-offs",
    }
    return labels.get(s, str(stage).replace("_", " ").title())


def _competition_meta_from_fdo(match: Dict[str, Any]) -> Dict[str, Any]:
    comp = match.get("competition")
    meta: Dict[str, Any] = {}
    if isinstance(comp, dict):
        cn = (comp.get("name") or "").strip()
        if cn:
            meta["fdo_competition_name"] = cn
    rnd = _fdo_round_from_match(match)
    if rnd:
        meta["api_round"] = rnd
    return meta


def _competition_meta_from_fotmob(match: Dict[str, Any]) -> Dict[str, Any]:
    fm = match.get("_fotmob_league")
    if not isinstance(fm, dict):
        return {}
    nm = (fm.get("name") or "").strip()
    return {"fotmob_league_name": nm} if nm else {}


def _normalize_api_sports(fixture: Dict, league_code: str) -> Optional[Dict]:
    fm = fixture.get("fixture", {})
    home = fixture.get("teams", {}).get("home", {})
    away = fixture.get("teams", {}).get("away", {})
    if not fm or not home or not away:
        return None
    comp_meta = _competition_meta_from_api_sports(fixture)
    return {
        "fixture": {"id": fm.get("id"), "date": fm.get("date"), "status": fm.get("status", {})},
        "teams": {
            "home": {"id": home.get("id", 0), "name": home.get("name", "?")},
            "away": {"id": away.get("id", 0), "name": away.get("name", "?")},
        },
        "home": {"id": home.get("id", 0), "name": home.get("name", "?")},
        "away": {"id": away.get("id", 0), "name": away.get("name", "?")},
        "date": fm.get("date"),
        "league": league_code,
        "competition_meta": comp_meta,
    }


def _normalize_fdo(match: Dict, league_code: str) -> Optional[Dict]:
    if not match:
        return None
    home = match.get("homeTeam", {}) or {}
    away = match.get("awayTeam", {}) or {}
    date = match.get("utcDate")
    if not date or not home or not away:
        return None
    comp_meta = _competition_meta_from_fdo(match)
    return {
        "fixture": {"id": match.get("id"), "date": date, "status": {"short": match.get("status", "")}},
        "teams": {
            "home": {"id": home.get("id", 0), "name": home.get("name", "?")},
            "away": {"id": away.get("id", 0), "name": away.get("name", "?")},
        },
        "home": {"id": home.get("id", 0), "name": home.get("name", "?")},
        "away": {"id": away.get("id", 0), "name": away.get("name", "?")},
        "date": date,
        "league": league_code,
        "competition_meta": comp_meta,
    }


def _normalize_fotmob(match: Dict, league_code: str) -> Optional[Dict]:
    """Normalize a FotMob public daily-match row into the app fixture shape."""
    if not match:
        return None
    home = match.get("home") or {}
    away = match.get("away") or {}
    home_name = (home.get("longName") or home.get("name")) if isinstance(home, dict) else None
    away_name = (away.get("longName") or away.get("name")) if isinstance(away, dict) else None
    status = match.get("status") if isinstance(match.get("status"), dict) else {}
    date_s = (
        match.get("utcTime")
        or status.get("utcTime")
        or match.get("time")
        or match.get("date")
    )
    mid = match.get("id") or match.get("matchId")
    hid = home.get("id") if isinstance(home, dict) else 0
    aid = away.get("id") if isinstance(away, dict) else 0
    if not home_name or not away_name or not date_s:
        return None
    comp_meta = _competition_meta_from_fotmob(match)
    return {
        "fixture": {
            "id": f"fotmob_{mid}" if mid else None,
            "date": date_s,
            "status": {
                "short": status.get("reason", {}).get("short")
                if isinstance(status.get("reason"), dict)
                else match.get("status")
            },
        },
        "teams": {
            "home": {"id": hid or 0, "name": home_name},
            "away": {"id": aid or 0, "name": away_name},
        },
        "home": {"id": hid or 0, "name": home_name},
        "away": {"id": aid or 0, "name": away_name},
        "date": date_s,
        "league": league_code,
        "competition_meta": comp_meta,
        "source": "fotmob_public",
    }


def fetch_next_48h_fixtures(league_code: str, *, allow_stale: bool = False) -> List[Dict]:
    days = _fixture_window_days_for_league(league_code)
    cache = Cache()
    from hibs_predictor.scrape_first import fixture_fetch_flags

    prefer_fdo, skip_as_fx = fixture_fetch_flags()
    ttl = _cache_ttl_hours(1.0)
    cache_key = f"fixtures_{days}d_{league_code}_{_FIXTURE_CACHE_VERSION}_{int(prefer_fdo)}{int(skip_as_fx)}"
    guard_blocked = _provider_guard_blocked("api_sports")
    reuse_stale = allow_stale or guard_blocked
    cached = cache.get(cache_key, ttl_hours=ttl)
    stale_rows = cached if isinstance(cached, list) else _stale_league_fixture_rows(cache, cache_key)
    if cached is None and reuse_stale and stale_rows:
        cached = stale_rows
    if cached:
        if _league_fixture_cache_fresh(cached):
            return cached
        if reuse_stale:
            if guard_blocked or cached is stale_rows:
                _log_resilience(
                    "league_fixture_stale_reuse",
                    league=league_code,
                    guard_blocked=guard_blocked,
                    rows=len(cached),
                )
            return cached
        _hibs_debug_log(f"partial enrich cache bust {league_code} key={cache_key}")

    league = LEAGUES.get(league_code, {})
    now = datetime.now(timezone.utc)
    window_start = fixture_window_start_utc(now)
    cutoff = fixture_window_end_utc(now, days)
    fetched: Dict[str, Dict] = {}
    date_from = window_start.strftime("%Y-%m-%d")
    date_to = cutoff.strftime("%Y-%m-%d")
    fdo_comp = league.get("football_data_org_id")
    season_candidates = _fixture_fetch_season_candidates(
        fdo_comp, date_from, date_to, now, league_code=league_code
    )
    if league_code == "INTL_FRIENDLIES":
        y = now.year
        season_candidates = [y, y - 1] + [s for s in season_candidates if s not in (y, y - 1)]

    def add(candidate: Dict) -> None:
        key = _fixture_key(candidate)
        if key and key not in fetched:
            fetched[key] = candidate

    league_api_id = league.get("api_sports_id")

    def try_api_sports() -> None:
        if skip_as_fx or "api_sports" not in aggregator.clients or not league_api_id:
            return
        try:
            for season in season_candidates:
                raw = aggregator.clients["api_sports"].fetch_fixtures_by_league(
                    int(league_api_id),
                    int(season),
                    date_from=date_from,
                    date_to=date_to,
                )
                for f in raw or []:
                    norm = _normalize_api_sports(f, league_code)
                    if not norm:
                        continue
                    try:
                        raw_date = norm.get("date") or ""
                        fd = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
                        if window_start <= fd <= cutoff:
                            norm["date"] = fd.isoformat()
                            add(norm)
                    except (TypeError, ValueError, OSError) as parse_err:
                        print(f"[API-Sports date] {league_code}: {parse_err} raw={norm.get('date')!r}")
                        continue
                if fetched:
                    break
        except Exception as e:
            print(f"[API-Sports] {league_code}: {e!r}")

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

                _time.sleep(0.5)
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
                        fd = datetime.fromisoformat(norm["date"].replace("Z", "+00:00"))
                    except Exception:
                        continue
                    if st in ("CANCELLED", "POSTPONED", "ABANDONED", "SUSPENDED"):
                        continue
                    if st in ("FINISHED", "AWARDED") and fd < window_start:
                        continue
                    if window_start <= fd <= cutoff:
                        norm["date"] = fd.isoformat()
                        add(norm)
                if fetched:
                    break
            except Exception as ex:
                print(f"[Football-Data.org] {league_code} {comp} season={season}: {ex!r}")
                continue

    def try_fotmob() -> None:
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
        except Exception as ex:
            _hibs_debug_log(f"[FotMob] {league_code}: {ex!r}")

    def try_espn() -> None:
        try:
            from hibs_predictor.scrapers.espn_client import espn_fixtures_enabled, fixtures_for_league

            if not espn_fixtures_enabled():
                return
            day = window_start.date()
            end_day = cutoff.date()
            for norm in fixtures_for_league(league_code, day, end_day, cache=cache) or []:
                try:
                    fd = datetime.fromisoformat(str(norm.get("date") or "").replace("Z", "+00:00"))
                    if window_start <= fd <= cutoff:
                        norm["date"] = fd.isoformat()
                        add(norm)
                except Exception:
                    continue
        except Exception as ex:
            _hibs_debug_log(f"[ESPN] {league_code}: {ex!r}")

    api_first = league_code in _API_FIRST_FIXTURE_LEAGUES
    if api_first or not prefer_fdo:
        try_api_sports()
        if not fetched:
            try_football_data()
    else:
        try_football_data()
        if not fetched:
            try_api_sports()
    if not fetched:
        try_fotmob()
    if not fetched:
        try_espn()

    _hibs_debug_log(
        f"fixtures {league_code} days={days} count={len(fetched)} api_first={api_first} prefer_fdo={prefer_fdo}"
    )

    stale_by_key = _stale_fixture_row_index(stale_rows)
    fixtures = []
    from hibs_predictor.enrich_chunk import chunked_enrich_enabled, enrich_chunk_pause_seconds, enrich_chunk_size

    enrich_chunk_i = 0
    for fixture in fetched.values():
        fix_key = _fixture_key(fixture)
        if _provider_guard_blocked("api_sports"):
            stale_row = stale_by_key.get(fix_key)
            if stale_row:
                fixtures.append(dict(stale_row))
                continue
        enriched = _safe_enrich(fixture, league_code)
        enrich_chunk_i += 1
        if chunked_enrich_enabled() and enrich_chunk_i % enrich_chunk_size() == 0:
            import time

            time.sleep(enrich_chunk_pause_seconds())
        try:
            prediction = betting_engine.predict_with_confidence(enriched)
        except Exception as e:
            print(f"[Prediction] {league_code} {_fixture_key(fixture)}: {e!r}")
            prediction = prediction_unavailable_payload(enriched, "model_error")

        from hibs_predictor.fixture_utils import fixture_team_id, fixture_team_name

        home_id = (
            fixture_team_id(enriched, "home")
            or fixture.get("home_id")
            or fixture_team_id(fixture, "home")
        )
        away_id = (
            fixture_team_id(enriched, "away")
            or fixture.get("away_id")
            or fixture_team_id(fixture, "away")
        )
        home_nm = fixture_team_name(enriched, "home") or str(fixture.get("home") or "")
        away_nm = fixture_team_name(enriched, "away") or str(fixture.get("away") or "")
        home_last10: List[Dict[str, Any]] = []
        away_last10: List[Dict[str, Any]] = []
        try:
            home_last10 = TeamStrengthCalculator.parse_last_10_results(
                enriched.get("home_recent", []), home_id, team_name=home_nm
            )
        except Exception as e:
            print(f"[Fixture last10 home] {league_code} {_fixture_key(fixture)}: {e!r}")
        try:
            away_last10 = TeamStrengthCalculator.parse_last_10_results(
                enriched.get("away_recent", []), away_id, team_name=away_nm
            )
        except Exception as e:
            print(f"[Fixture last10 away] {league_code} {_fixture_key(fixture)}: {e!r}")
        if home_id and not home_last10 and enriched.get("home_recent"):
            print(
                f"[Fixture last10 home] {league_code} {_fixture_key(fixture)}: "
                f"id={home_id} had {len(enriched.get('home_recent') or [])} raw matches but 0 parsed"
            )
        if away_id and not away_last10 and enriched.get("away_recent"):
            print(
                f"[Fixture last10 away] {league_code} {_fixture_key(fixture)}: "
                f"id={away_id} had {len(enriched.get('away_recent') or [])} raw matches but 0 parsed"
            )

        comp_meta = enriched.get("competition_meta") if isinstance(enriched.get("competition_meta"), dict) else {}
        if not comp_meta and isinstance(fixture.get("competition_meta"), dict):
            comp_meta = fixture.get("competition_meta") or {}
        fb_name = LEAGUES.get(league_code, {}).get("name", league_code)
        title = display_competition_title(
            fallback_name=fb_name,
            api_league_name=comp_meta.get("api_league_name"),
            api_round=comp_meta.get("api_round"),
            fotmob_league_name=comp_meta.get("fotmob_league_name"),
            fdo_competition_name=comp_meta.get("fdo_competition_name"),
        )

        raw_fid = fixture.get("fixture", {}).get("id")
        from hibs_predictor.live_scores import parse_fixture_id_int

        api_fid = parse_fixture_id_int(raw_fid)
        row = {
            "id": raw_fid,
            "api_fixture_id": api_fid,
            "source": fixture.get("source"),
            "home": home_nm or "?",
            "away": away_nm or "?",
            "home_id": home_id,
            "away_id": away_id,
            "date": fixture.get("date"),
            "fixture_status": fixture_status_short(fixture),
            "league": league_code,
            "league_name": title,
            "competition_meta": comp_meta,
            "league_flag": LEAGUES.get(league_code, {}).get("flag", ""),
            "enriched_at": enriched.get("enriched_at"),
            "prediction": prediction,
            "home_last10": home_last10,
            "away_last10": away_last10,
            "home_recent_n": _safe_int_value(
                enriched.get("home_recent_n") or len(home_last10) or len(enriched.get("home_recent") or [])
            ),
            "away_recent_n": _safe_int_value(
                enriched.get("away_recent_n") or len(away_last10) or len(enriched.get("away_recent") or [])
            ),
            "home_position": enriched.get("home_position", {}),
            "away_position": enriched.get("away_position", {}),
            "home_stats": enriched.get("home_stats"),
            "away_stats": enriched.get("away_stats"),
            "all_bookmaker_odds": enriched.get("all_bookmaker_odds", []),
            "fixture_injuries": enriched.get("fixture_injuries", []),
            "attack_availability_home": enriched.get("attack_availability_home"),
            "attack_availability_away": enriched.get("attack_availability_away"),
            "team_news_meta": enriched.get("team_news_meta") or {},
            "home_top_scorers": enriched.get("home_top_scorers") or [],
            "away_top_scorers": enriched.get("away_top_scorers") or [],
            "lineup_confirmed": bool(enriched.get("lineup_confirmed")),
            "fixture_lineups": enriched.get("fixture_lineups"),
            "lineup_meta": enriched.get("lineup_meta") or {},
            "market_odds": enriched.get("market_odds", {}),
            "supplemental": enriched.get("supplemental", {}),
            "xg_home": enriched.get("xg_home"),
            "xg_away": enriched.get("xg_away"),
            "xg_source": enriched.get("xg_source", "unknown"),
            "xg_source_label": enriched.get("xg_source_label"),
            "xg_confidence_tier": enriched.get("xg_confidence_tier"),
            "xg_source_hint": enriched.get("xg_source_hint"),
            "scraped_xg_meta": enriched.get("scraped_xg_meta") or {},
            "best_odds_1x2": enriched.get("best_odds_1x2") or {},
            "best_odds_source": enriched.get("best_odds_source") or {},
            "sharp_anchor_implied": enriched.get("sharp_anchor_implied") or {},
            "has_value_bet": bool(
                prediction.get("has_any_value")
                or prediction.get("value_bets")
                or prediction.get("value_bets_alt")
            ),
        }
        row["data_quality"] = _data_quality_for_enriched(enriched, prediction)
        _merge_stale_fixture_row(row, stale_by_key.get(_fixture_key(fixture)))
        if _maybe_rerun_prediction_after_stale_merge(row):
            prediction = row["prediction"]
        try:
            from hibs_predictor.xg_source_display import attach_xg_display_fields, compact_fixture_xg

            attach_xg_display_fields(row, enriched)
            cxh, cxa = compact_fixture_xg(row, prediction=prediction)
            if cxh is not None:
                row["compact_xg_home"] = cxh
            if cxa is not None:
                row["compact_xg_away"] = cxa
        except Exception as exc:
            print(f"[Fixture compact_xg] {league_code} {_fixture_key(fixture)}: {exc!r}")
        fixtures.append(row)

    fixtures.sort(key=lambda x: x.get("date") or "")
    disk_rows = [row for row in fixtures if _slim_row_enrich_fresh(row)]
    disk_rows = _merge_league_fixture_lists(disk_rows, stale_rows)
    if stale_rows and disk_rows:
        old_fresh = sum(1 for row in stale_rows if _slim_row_enrich_fresh(row))
        new_fresh = sum(1 for row in disk_rows if _slim_row_enrich_fresh(row))
        if old_fresh > new_fresh:
            _log_resilience(
                "league_fixture_keep_stale_cache",
                league=league_code,
                old_fresh=old_fresh,
                new_fresh=new_fresh,
            )
            return stale_rows
    if disk_rows:
        cache.set(
            cache_key,
            disk_rows,
            ttl_hours=ttl if disk_rows else _EMPTY_FIXTURE_CACHE_TTL_HOURS,
        )
    return _merge_league_fixture_lists(fixtures, stale_rows)


def _data_quality_for_enriched(enriched: Dict[str, Any], prediction: Dict[str, Any]) -> Dict[str, Any]:
    """Score coverage after prediction so line_odds and book prices count toward the bar."""
    from hibs_predictor.data_quality import compute_fixture_data_quality

    scoring = dict(enriched)
    if enriched.get("league"):
        scoring.setdefault("league", enriched.get("league"))
    scoring["prediction"] = prediction
    lo = prediction.get("line_odds") or {}
    if lo:
        scoring["line_odds"] = lo
    bo = prediction.get("bookmaker_odds") or {}
    if bo and not scoring.get("odds_available"):
        try:
            scoring["odds_available"] = all(float(bo.get(k) or 0) > 1.0 for k in ("home", "draw", "away"))
        except (TypeError, ValueError):
            pass
        scoring.setdefault("odds_home", bo.get("home"))
        scoring.setdefault("odds_draw", bo.get("draw"))
        scoring.setdefault("odds_away", bo.get("away"))
    return compute_fixture_data_quality(scoring)


def _reboost_bundle_data_quality(all_fixtures: List[Dict[str, Any]]) -> None:
    """Deep-enrich thin rows after a cold cache (developer / HIBS_BUNDLE_DQ_REBOOST)."""
    from hibs_predictor.deep_enrich import reboost_dashboard_data_quality

    try:
        n = reboost_dashboard_data_quality(aggregator, all_fixtures)
        if n:
            print(f"[DQ reboost] upgraded {n} fixture row(s) toward target")
    except Exception as exc:
        print(f"[DQ reboost] failed: {exc!r}")


def _ensure_fixture_data_quality(all_fixtures: List[Dict[str, Any]]) -> None:
    """Backfill missing data_quality only — never re-score rows that already have a score (avoids DQ cliffs)."""
    from hibs_predictor.data_quality import compute_fixture_data_quality_from_row
    from hibs_predictor.xg_source_display import attach_xg_display_fields

    for f in all_fixtures:
        existing = f.get("data_quality") if isinstance(f.get("data_quality"), dict) else {}
        if existing.get("score_pct") is not None:
            try:
                existing_pct = float(existing["score_pct"])
            except (TypeError, ValueError):
                existing_pct = None
            if existing_pct is not None and existing_pct >= 85.0:
                continue
            if existing_pct is not None and not _slim_row_enrich_fresh(f):
                continue
        if not f.get("xg_source_hint"):
            attach_xg_display_fields(f)
        try:
            fresh_dq = compute_fixture_data_quality_from_row(f)
            if existing.get("score_pct") is not None:
                try:
                    old_pct = float(existing["score_pct"])
                    new_pct = float(fresh_dq.get("score_pct") or 0)
                    if new_pct <= old_pct:
                        continue
                except (TypeError, ValueError):
                    pass
            f["data_quality"] = fresh_dq
        except Exception as exc:
            print(f"[Data quality] {f.get('home')} v {f.get('away')}: {exc!r}")


def _ensure_fixture_pick_menus(all_fixtures: List[Dict[str, Any]]) -> None:
    """Backfill pick_menu / structured_insight on cached rows from older bundle versions."""
    from hibs_predictor.match_insight import attach_structured_insight

    for f in all_fixtures:
        p = f.get("prediction")
        if not isinstance(p, dict):
            continue
        if p.get("pick_menu"):
            continue
        try:
            attach_structured_insight(f, p)
        except Exception as exc:
            print(f"[Pick menu] {f.get('home')} v {f.get('away')}: {exc!r}")


def _safe_int_value(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _table_team_display(value: Any) -> str:
    """Render-safe team label from API dict or plain string."""
    return table_team_display(value)


def _table_team_id(value: Any) -> Optional[int]:
    from hibs_predictor.fixture_utils import coerce_team_id

    if isinstance(value, dict):
        return coerce_team_id(value.get("id"))
    return None


def _normalize_position_rank(value: Any) -> Optional[int]:
    """Integer table rank; never pass through nested team dicts."""
    return normalize_position_rank(value)


def _team_key(name: Any) -> str:
    from hibs_predictor.team_aliases import team_key

    return team_key(_table_team_display(name))


def _canonical_team_key(name: Any) -> str:
    from hibs_predictor.team_aliases import canonical_team_key

    return canonical_team_key(_table_team_display(name))


def _team_names_match(a: str, b: str) -> bool:
    """Loose match for fixture display names vs standings (e.g. Hibs vs Hibernian)."""
    from hibs_predictor.team_aliases import team_names_match

    return team_names_match(a, b)


def _normalize_table_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure table rows use string team names and integer ranks for templates."""
    out = dict(row)
    team_raw = out.get("team")
    tid = out.get("team_id") or _table_team_id(team_raw)
    if tid is not None:
        out["team_id"] = tid
    name = _table_team_display(team_raw) or _table_team_display(out.get("team_name"))
    if name:
        out["team"] = name
    rank = _normalize_position_rank(out.get("position"))
    if rank is not None:
        out["position"] = rank
    elif out.get("position") is not None:
        out.pop("position", None)
    for key in ("played", "won", "drawn", "lost", "goals_for", "goals_against", "goal_diff", "points"):
        if key in out:
            out[key] = _safe_int_value(out.get(key))
    form = out.get("form")
    if form is not None and not isinstance(form, str):
        out["form"] = str(form)
    return out


def _normalize_position_dict(pos: Any) -> Dict[str, Any]:
    """Sanitize home/away position blobs attached to fixtures."""
    return normalize_position_dict(pos)


def _table_row_dedupe_key(row: Dict[str, Any]) -> str:
    tid = row.get("team_id")
    if tid:
        return f"id:{tid}"
    key = _canonical_team_key(row.get("team"))
    return f"n:{key}" if key else ""


_SCOTLAND_SPLIT_LEAGUES = frozenset({"SCOTLAND"})


def _iter_total_standings_entry_lists(groups: Any):
    """Yield flat team-entry lists from API-Sports / Football-Data standings payloads."""
    for group in groups or []:
        if isinstance(group, dict):
            if str(group.get("type") or "").upper() not in ("TOTAL", ""):
                continue
            entries = group.get("table") or []
            if entries:
                yield entries
        elif isinstance(group, list):
            if not group:
                continue
            if isinstance(group[0], dict) and ("rank" in group[0] or "team" in group[0]):
                yield group
            else:
                for sub in group:
                    if isinstance(sub, list) and sub and isinstance(sub[0], dict):
                        yield sub


def _entry_max_played(entry: Dict[str, Any]) -> int:
    all_stats = entry.get("all") or {}
    return _safe_int_value(all_stats.get("played"), 0)


def _merge_scottish_split_standings(groups: Any) -> List[Dict[str, Any]]:
    """Merge SPFL regular season + championship/relegation splits into one 38-game table."""
    rows_by_key: Dict[str, Dict[str, Any]] = {}
    for entries in _iter_total_standings_entry_lists(groups):
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            row = _table_row_from_api_entry(entry)
            if not row:
                continue
            key = _table_row_dedupe_key(row)
            if not key or key == "n:":
                name_key = _canonical_team_key(row.get("team"))
                if not name_key:
                    continue
                key = f"n:{name_key}"
            existing = rows_by_key.get(key)
            if existing is None or (row.get("played") or 0) > (existing.get("played") or 0):
                rows_by_key[key] = row
    if len(rows_by_key) < 10:
        return []
    return sorted(
        rows_by_key.values(),
        key=lambda r: (_safe_int_value(r.get("position"), 999), str(r.get("team") or "")),
    )


def _pick_best_standings_group(groups: Any, league_code: str = "") -> List[Any]:
    """Pick standings with the most games played (38-game split > 33-game regular)."""
    best_entries: List[Any] = []
    best_max_played = -1
    best_len = 0
    for entries in _iter_total_standings_entry_lists(groups):
        if not entries:
            continue
        max_played = max((_entry_max_played(e) for e in entries if isinstance(e, dict)), default=0)
        n = len(entries)
        if max_played > best_max_played or (max_played == best_max_played and n > best_len):
            best_max_played = max_played
            best_len = n
            best_entries = list(entries)
    return best_entries


def _standings_rows_from_groups(groups: Any, league_code: str) -> List[Dict[str, Any]]:
    if league_code in _SCOTLAND_SPLIT_LEAGUES:
        merged = _merge_scottish_split_standings(groups)
        if merged:
            return merged
    entries = _pick_best_standings_group(groups, league_code)
    return [
        row
        for entry in entries
        for row in [_table_row_from_api_entry(entry)]
        if row
    ]


def _pick_largest_standings_group(groups: Any) -> List[Any]:
    """Legacy helper — prefer ``_pick_best_standings_group`` / ``_standings_rows_from_groups``."""
    return _pick_best_standings_group(groups, "")


def _find_table_row_index(
    rows: List[Dict[str, Any]],
    team: str,
    position_hint: Optional[Dict[str, Any]] = None,
) -> Optional[int]:
    key = _canonical_team_key(team)
    if key:
        for i, row in enumerate(rows):
            if _canonical_team_key(row.get("team")) == key:
                return i
        for i, row in enumerate(rows):
            if _team_names_match(key, _team_key(row.get("team"))):
                return i
    if position_hint and position_hint.get("position") not in (None, "", "?"):
        pos = _normalize_position_rank(position_hint.get("position")) or 999
        if pos != 999:
            for i, row in enumerate(rows):
                if _normalize_position_rank(row.get("position")) == pos:
                    return i
    return None


def _table_row_from_position(team: str, position: Dict[str, Any], source: str = "fixture") -> Optional[Dict[str, Any]]:
    if not isinstance(position, dict):
        return None
    rank = _normalize_position_rank(position.get("position", position.get("rank")))
    if rank is None:
        return None
    team_name = _table_team_display(team) or _table_team_display(position.get("team")) or "Unknown"
    row = {
        "position": rank,
        "team": team_name,
        "played": _safe_int_value(position.get("played")),
        "won": _safe_int_value(position.get("won")),
        "drawn": _safe_int_value(position.get("drawn")),
        "lost": _safe_int_value(position.get("lost")),
        "goals_for": _safe_int_value(position.get("goals_for")),
        "goals_against": _safe_int_value(position.get("goals_against")),
        "goal_diff": _safe_int_value(position.get("goal_diff")),
        "points": _safe_int_value(position.get("points")),
        "form": position.get("form") or "",
        "source": position.get("source") or source,
    }
    tid = _table_team_id(position.get("team"))
    if tid is not None:
        row["team_id"] = tid
    return _normalize_table_row(row)


def _table_row_from_api_entry(entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    team_obj = entry.get("team") if isinstance(entry.get("team"), dict) else {}
    team = _table_team_display(team_obj) or _table_team_display(entry.get("team_name")) or _table_team_display(entry.get("team"))
    all_stats = entry.get("all") or {}
    goals = all_stats.get("goals") or {}
    row = _table_row_from_position(
        team,
        {
            "position": entry.get("rank"),
            "played": all_stats.get("played"),
            "won": all_stats.get("win"),
            "drawn": all_stats.get("draw"),
            "lost": all_stats.get("lose"),
            "goals_for": goals.get("for"),
            "goals_against": goals.get("against"),
            "goal_diff": entry.get("goalsDiff"),
            "points": entry.get("points"),
            "form": entry.get("form"),
            "source": "api_sports",
            "team": team_obj or None,
        },
    )
    if row and team_obj:
        tid = _table_team_id(team_obj)
        if tid is not None:
            row["team_id"] = tid
    return row


def _table_row_from_fdo_entry(entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    team_obj = entry.get("team") if isinstance(entry.get("team"), dict) else {}
    team = _table_team_display(team_obj) or _table_team_display(entry.get("team_name")) or _table_team_display(entry.get("team"))
    row = _table_row_from_position(
        team,
        {
            "position": entry.get("position"),
            "played": entry.get("playedGames"),
            "won": entry.get("won"),
            "drawn": entry.get("draw"),
            "lost": entry.get("lost"),
            "goals_for": entry.get("goalsFor"),
            "goals_against": entry.get("goalsAgainst"),
            "goal_diff": entry.get("goalDifference"),
            "points": entry.get("points"),
            "form": entry.get("form"),
            "source": "football_data_org",
            "team": team_obj or None,
        },
    )
    if row and team_obj:
        tid = _table_team_id(team_obj)
        if tid is not None:
            row["team_id"] = tid
    return row


def _season_status_for_rows(rows: List[Dict[str, Any]], season: int, primary_season: int) -> List[Dict[str, Any]]:
    if season == primary_season:
        return rows
    out = []
    for row in rows:
        r = dict(row)
        r.setdefault("season_status", "last_completed")
        out.append(r)
    return out


def _fetch_full_table_rows(league_code: str, *, live_fetch: Optional[bool] = None) -> List[Dict[str, Any]]:
    """Best-effort full standings for the tables page; callers fall back to fixture rows.

    Dashboard snapshots read existing cache only; /tables can live-fetch from
    configured documented API clients and falls back to previous season rows
    when the current/ended competition has no table in the active season id.
    """
    if is_cup_competition(league_code):
        return []
    from hibs_predictor.season import season_candidates

    league = LEAGUES.get(league_code) or {}
    league_api_id = league.get("api_sports_id")
    fdo_comp = league.get("football_data_org_id")
    now = datetime.now(timezone.utc)
    seasons = season_candidates(now, league_code=league_code)
    primary_season = seasons[0] if seasons else _api_football_season_year(now)
    allow_live = _env_truthy("HIBS_TABLES_LIVE_FETCH") if live_fetch is None else (bool(live_fetch) or _env_truthy("HIBS_TABLES_LIVE_FETCH"))
    standings_cache_ttl = 24 if allow_live else 48
    if league_api_id and "api_sports" in aggregator.clients and not _env_truthy("HIBS_SKIP_API_STANDINGS"):
        for season in seasons:
            try:
                params = {"league": int(league_api_id), "season": int(season)}
                groups_payload = aggregator.clients["api_sports"].cache.get(
                    f"api_sports_standings_{str(params)}", ttl_hours=standings_cache_ttl
                )
                if groups_payload:
                    response = groups_payload.get("response", []) if isinstance(groups_payload, dict) else []
                    groups = response[0].get("league", {}).get("standings", [[]]) if response else [[]]
                elif allow_live:
                    groups = aggregator.clients["api_sports"].fetch_standings(int(league_api_id), int(season))
                else:
                    groups = []
                rows = _standings_rows_from_groups(groups, league_code)
                if rows:
                    return _season_status_for_rows(rows, season, primary_season)
            except Exception as exc:
                print(f"[Tables api_sports] {league_code}: {exc!r}")
                continue
    if fdo_comp and "football_data_org" in aggregator.clients:
        for season in seasons:
            try:
                params = {"season": int(season)}
                payload = aggregator.clients["football_data_org"].cache.get(
                    f"football_data_org_competitions/{fdo_comp}/standings_{str(params)}", ttl_hours=standings_cache_ttl
                )
                if isinstance(payload, dict):
                    groups = payload.get("standings", []) or []
                elif allow_live:
                    groups = aggregator.clients["football_data_org"].fetch_standings(str(fdo_comp), int(season))
                else:
                    groups = []
                entries = _pick_best_standings_group(groups, league_code)
                rows = [
                    row
                    for entry in entries
                    for row in [_table_row_from_fdo_entry(entry)]
                    if row
                ]
                if rows:
                    return _season_status_for_rows(rows, season, primary_season)
            except Exception as exc:
                print(f"[Tables football_data] {league_code}: {exc!r}")
                continue
    try:
        from hibs_predictor.scrapers import soccerstats_standings as ss_standings

        if league_code not in ss_standings.LEAGUE_PARAM:
            return []
        cached = aggregator.cache.get(f"soccerstats_table_{league_code}", ttl_hours=12)
        if cached is None and allow_live:
            cached = aggregator._cached_soccerstats_league_table(league_code)
        rows = [
            _table_row_from_position(str(r.get("team") or ""), ss_standings.row_to_position_shape(r), "soccerstats")
            for r in (cached or [])
        ]
        return [r for r in rows if r]
    except Exception as exc:
        print(f"[Tables soccerstats] {league_code}: {exc!r}")
    return []


def _fixture_position_rows(fixtures: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    by_league: Dict[str, List[Dict[str, Any]]] = {}
    for fixture in fixtures:
        league_code = fixture.get("league") or ""
        if not league_code:
            continue
        for team_key, pos_key in (("home", "home_position"), ("away", "away_position")):
            row = _table_row_from_position(fixture_team_name(fixture, team_key), fixture.get(pos_key) or {})
            if row:
                by_league.setdefault(league_code, []).append(row)
    return by_league


def _dedupe_table_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized = [_normalize_table_row(r) for r in rows]
    by_key: Dict[str, Dict[str, Any]] = {}
    name_to_key: Dict[str, str] = {}

    def _prefer(existing: Dict[str, Any], candidate: Dict[str, Any]) -> bool:
        if existing.get("source") == "fixture" and candidate.get("source") != "fixture":
            return True
        if candidate.get("team_id") and not existing.get("team_id"):
            return True
        cand_played = _safe_int_value(candidate.get("played"), 0)
        exist_played = _safe_int_value(existing.get("played"), 0)
        if cand_played > exist_played:
            return True
        if exist_played > cand_played:
            return False
        return False

    for row in normalized:
        name_key = _canonical_team_key(row.get("team"))
        key = _table_row_dedupe_key(row)
        if name_key and name_key in name_to_key:
            key = name_to_key[name_key]
        elif not key or key == "n:":
            if not name_key:
                continue
            key = f"n:{name_key}"
        existing = by_key.get(key)
        if existing is None or _prefer(existing, row):
            by_key[key] = row
            if name_key:
                name_to_key[name_key] = key
    seen_ids: set[int] = set()
    unique: List[Dict[str, Any]] = []
    for row in by_key.values():
        tid = row.get("team_id")
        if tid:
            if tid in seen_ids:
                continue
            seen_ids.add(int(tid))
        unique.append(row)
    return sorted(unique, key=lambda r: (_safe_int_value(r.get("position"), 999), str(r.get("team") or "")))


def _tables_league_order_index(*, include_domestic: bool = False) -> Dict[str, int]:
    """League block order on /tables — World Cup first when tournament focus is on."""
    from hibs_predictor.config import DASHBOARD_LEAGUE_ORDER
    from hibs_predictor.tournament_focus import active_competition_league_codes, tournament_focus_active

    if tournament_focus_active():
        focus = active_competition_league_codes()
        if include_domestic:
            order = focus + [c for c in DASHBOARD_LEAGUE_ORDER if c not in focus]
        else:
            order = focus
        return {c: i for i, c in enumerate(order)}
    return {c: i for i, c in enumerate(_dashboard_league_order(include_domestic=include_domestic))}


def _build_league_tables(
    fixtures: List[Dict[str, Any]], *, include_live: bool = False, include_domestic: bool = False
) -> List[Dict[str, Any]]:
    fixture_rows = _fixture_position_rows(fixtures)
    league_codes = set(fixture_rows)
    league_codes.update(str(f.get("league") or "") for f in fixtures if f.get("league"))
    if include_live:
        league_codes.update(_dashboard_league_order())
    order_index = _tables_league_order_index(include_domestic=include_domestic)
    tables: List[Dict[str, Any]] = []
    for league_code in sorted(league_codes, key=lambda c: (order_index.get(c, 999), c)):
        rows: List[Dict[str, Any]] = []
        full_rows = _fetch_full_table_rows(league_code, live_fetch=include_live)
        rows.extend(full_rows)
        rows.extend(fixture_rows.get(league_code, []))
        rows = _dedupe_table_rows(rows)
        used_last_completed = any(row.get("season_status") == "last_completed" for row in rows)
        display_name = LEAGUES.get(league_code, {}).get("name", league_code)
        league_fixtures = [f for f in fixtures if f.get("league") == league_code]
        if league_fixtures:
            display_name = _league_block_display_name(league_code, league_fixtures)
        tables.append(
            {
                "code": league_code,
                "name": display_name,
                "rows": rows,
                "source": rows[0].get("source") if rows else "",
                "is_partial": len(rows) < 8,
                "season_status": "last_completed" if used_last_completed else "current",
                "status_note": (
                    "Latest completed-season standings used because current fixtures/tables are thin."
                    if used_last_completed
                    else ""
                ),
            }
        )
    return tables


def _snapshot_for_team(
    rows: List[Dict[str, Any]],
    team: str,
    position_hint: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    idx = _find_table_row_index(rows, team, position_hint)
    if idx is not None:
        start = max(0, idx - 1)
        end = min(len(rows), idx + 2)
        snapshot = []
        for i, row in enumerate(rows[start:end], start=start):
            out = dict(row)
            out["is_focus"] = i == idx
            snapshot.append(out)
        return snapshot
    row = _table_row_from_position(team, position_hint or {})
    if row:
        out = dict(row)
        out["is_focus"] = True
        return [out]
    return []


def _attach_cup_and_form_flags(fixtures: List[Dict[str, Any]]) -> None:
    for fixture in fixtures:
        lc = fixture.get("league") or ""
        fixture["is_cup_competition"] = is_cup_competition(lc)
        if fixture["is_cup_competition"]:
            fixture["cup_round_label"] = cup_round_label(fixture)
        hp = fixture.get("home_position") or {}
        ap = fixture.get("away_position") or {}
        fixture["home_table_form_warn"] = table_form_inconsistent(hp, fixture.get("home_last10") or [])
        fixture["away_table_form_warn"] = table_form_inconsistent(ap, fixture.get("away_last10") or [])


def _attach_table_snapshots(fixtures: List[Dict[str, Any]], tables: List[Dict[str, Any]]) -> None:
    by_code = {t["code"]: t for t in tables}
    for fixture in fixtures:
        normalize_fixture_display(fixture)
        fixture["home_position"] = _normalize_position_dict(fixture.get("home_position"))
        fixture["away_position"] = _normalize_position_dict(fixture.get("away_position"))
        league_code = fixture.get("league") or ""
        is_cup = is_cup_competition(league_code)
        fixture["is_cup_competition"] = is_cup
        if is_cup:
            fixture["cup_round_label"] = cup_round_label(fixture)
            fixture["league_table_rows"] = []
            fixture["home_table_snapshot"] = []
            fixture["away_table_snapshot"] = []
            fixture["league_table_name"] = fixture.get("league_name") or league_code
            fixture["league_table_status_note"] = "Knockout cup — no league table; see round and recent form."
            continue
        tbl = by_code.get(league_code) or {}
        rows = [_normalize_table_row(r) for r in (tbl.get("rows") or [])]
        home = fixture_team_name(fixture, "home")
        away = fixture_team_name(fixture, "away")
        home_key = _canonical_team_key(home)
        away_key = _canonical_team_key(away)
        full_rows: List[Dict[str, Any]] = []
        for row in rows:
            out = dict(row)
            tk = _canonical_team_key(row.get("team"))
            out["is_home_team"] = bool(home_key and tk == home_key)
            out["is_away_team"] = bool(away_key and tk == away_key)
            if not out["is_home_team"] and not out["is_away_team"]:
                out["is_home_team"] = _team_names_match(home_key, tk)
                out["is_away_team"] = _team_names_match(away_key, tk)
            out["is_focus"] = out["is_home_team"] or out["is_away_team"]
            full_rows.append(out)
        fixture["league_table_rows"] = full_rows
        fixture["league_table_name"] = (
            _league_block_display_name(league_code, [fixture])
            if league_code
            else (fixture.get("league_name") or league_code)
        )
        fixture["league_table_status_note"] = tbl.get("status_note") or ""
        fixture["home_table_snapshot"] = _snapshot_for_team(
            rows, home, fixture.get("home_position")
        )
        fixture["away_table_snapshot"] = _snapshot_for_team(
            rows, away, fixture.get("away_position")
        )


def _upcoming_fixtures(all_fixtures: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Drop finished matches from the main upcoming dashboard list (still in Recent results)."""
    return [f for f in all_fixtures if not is_finished_fixture(f)]


def _fixtures_within_dashboard_window(
    fixtures: List[Dict[str, Any]],
    *,
    days: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Clip fixtures to the user-selected dashboard window (5 or 7 days).

    Wider league fetches (e.g. INTL_FRIENDLIES via HIBS_FRIENDLIES_FETCH_DAYS) stay in
    ``all`` for enrich/DQ; only display lists use this filter.
    """
    from hibs_predictor.data_source_policy import parse_fixture_datetime_utc

    window_days = (
        _normalize_fetch_days(days, default=_fetch_window_days())
        if days is not None
        else _fetch_window_days()
    )
    start = fixture_window_start_utc()
    end = fixture_window_end_utc(days=window_days)
    out: List[Dict[str, Any]] = []
    for fixture in fixtures:
        kick = parse_fixture_datetime_utc(fixture)
        if kick is not None and start <= kick <= end:
            out.append(fixture)
    return out


def _bundle_fixtures(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Upcoming-only fixture rows for dashboard/insights (finished same-day dropped)."""
    return data.get("upcoming") or _upcoming_fixtures(data.get("all") or [])


def _finalize_fixture_bundle(
    all_fixtures: List[Dict[str, Any]],
    *,
    attach_live: bool = False,
    include_domestic: bool = False,
    reboost: bool = False,
) -> Dict[str, Any]:
    from hibs_predictor.display_tz import enrich_fixtures_kickoff

    for row in all_fixtures:
        normalize_fixture_display(row)
    all_fixtures = enrich_fixtures_kickoff(all_fixtures)
    for row in all_fixtures:
        row["dashboard_region"] = league_dashboard_region(str(row.get("league") or ""))
    if attach_live:
        _refresh_live_on_bundle({"all": all_fixtures})
    _repair_guard_blocked_predictions(all_fixtures)
    _ensure_fixture_data_quality(all_fixtures)
    if reboost:
        _reboost_bundle_data_quality(all_fixtures)
    try:
        from hibs_predictor.betting_engine import apply_portfolio_kelly

        apply_portfolio_kelly(all_fixtures)
    except Exception as exc:
        print(f"[Portfolio Kelly] {exc!r}")
    try:
        from hibs_predictor.prediction_log import log_predictions_from_fixtures

        n_logged = log_predictions_from_fixtures(all_fixtures)
        if n_logged:
            print(f"[Prediction log] auto-logged {n_logged} snapshot(s)")
    except Exception as exc:
        print(f"[Prediction log] {exc!r}")
    try:
        from hibs_predictor.prediction_log import maybe_auto_sync_prediction_results

        sync_out = maybe_auto_sync_prediction_results()
        if sync_out.get("updated"):
            print(f"[Prediction log] results synced: {sync_out.get('message')}")
    except Exception as exc:
        print(f"[Prediction log sync] {exc!r}")
    _ensure_fixture_pick_menus(all_fixtures)
    all_fixtures.sort(key=lambda x: x.get("kickoff_sort") or x.get("date") or "")
    league_tables = _build_league_tables(all_fixtures, include_live=False, include_domestic=include_domestic)
    _attach_table_snapshots(all_fixtures, league_tables)
    _attach_cup_and_form_flags(all_fixtures)
    all_upcoming = _upcoming_fixtures(all_fixtures)
    upcoming = _fixtures_within_dashboard_window(all_upcoming)
    value_bets_only = [f for f in upcoming if f.get("has_value_bet")]
    value_bets_only.sort(key=lambda x: -(x.get("prediction", {}).get("best_bet_roi") or 0))
    fixtures_by_league: Dict[str, List] = {c: [] for c in _dashboard_league_order(include_domestic=include_domestic)}
    for f in upcoming:
        lc = f.get("league")
        if lc in fixtures_by_league:
            fixtures_by_league[lc].append(f)
    for c in fixtures_by_league:
        fixtures_by_league[c].sort(key=lambda x: x.get("kickoff_sort") or x.get("date") or "")
    by_region: Dict[str, List] = {r: [] for r in LEAGUE_REGIONS}
    for f in upcoming:
        for region, codes in LEAGUE_REGIONS.items():
            if f.get("league") in codes:
                by_region[region].append(f)
    coverage_summary = _fixture_coverage_summary(
        fixtures_by_league, len(upcoming), include_domestic=include_domestic
    )
    return {
        "all": all_fixtures,
        "upcoming": upcoming,
        "by_region": by_region,
        "by_league": fixtures_by_league,
        "dashboard_days": _dashboard_days_groups(upcoming, include_domestic=include_domestic),
        "value_bets": value_bets_only,
        "total": len(upcoming),
        "total_including_finished": len(all_fixtures),
        "value_bet_count": len(value_bets_only),
        "fetch_days": _fetch_window_days(),
        "has_api_clients": ("api_sports" in aggregator.clients or "football_data_org" in aggregator.clients),
        "sidebar_upcoming": _sidebar_upcoming(upcoming),
        "league_tables": league_tables,
        "fixture_coverage": coverage_summary,
    }


def _fixture_coverage_summary(
    by_league: Dict[str, List],
    total: int,
    *,
    include_domestic: bool = False,
) -> Dict[str, Any]:
    """User-facing note explaining why filter chips only show leagues with returned fixtures."""
    from hibs_predictor.tournament_focus import league_codes_for_fetch, tournament_focus_active

    focus_active = tournament_focus_active()
    intl_only = focus_active and not include_domestic
    fetch_codes = set(league_codes_for_fetch(include_domestic=include_domestic)) if focus_active else None
    loaded: List[Dict[str, Any]] = []
    empty: List[Dict[str, Any]] = []
    for code in _dashboard_league_order(include_domestic=include_domestic):
        if code not in LEAGUES:
            continue
        if fetch_codes is not None and code not in fetch_codes:
            continue
        league = LEAGUES[code]
        count = len(by_league.get(code) or [])
        row = {
            "code": code,
            "name": league.get("name", code),
            "count": count,
            "api_sports_id": league.get("api_sports_id"),
            "football_data_org_id": league.get("football_data_org_id"),
        }
        if count:
            loaded.append(row)
        else:
            empty.append(row)
    days = _fetch_window_days()
    configured_n = len(loaded) + len(empty)
    if intl_only:
        summary = (
            f"{len(loaded)} of {configured_n} international focus leagues returned fixtures "
            f"in the next {days} days."
        )
        reason = (
            "International focus mode is active — World Cup and international friendlies are fetched first. "
            "League of Ireland and Nordic leagues use the same dashboard window as full daily options — "
            "filter with Ireland or Nordic region chips. "
            "Use All / UK / European for other domestic leagues when needed."
        )
    elif focus_active:
        summary = (
            f"{len(loaded)} of {configured_n} configured leagues returned fixtures "
            f"in the next {days} days."
        )
        reason = (
            "World Cup focus is active but domestic leagues are included for this view "
            "(All / UK / European region selected). Filter chips reflect leagues with fixtures in the window."
        )
    else:
        summary = (
            f"{len(loaded)} of {configured_n} configured leagues returned fixtures "
            f"in the next {days} days."
        )
        reason = (
            "Filter chips are built only from leagues with fixtures in the current window. "
            "Empty leagues usually have no published matches in this date range, are outside the active season/cup window, "
            "have completed their season, or depend on a provider/plan that did not return fixtures."
        )
    return {
        "total_configured": configured_n,
        "loaded": loaded,
        "empty": empty,
        "loaded_count": len(loaded),
        "empty_count": len(empty),
        "empty_sample": empty[:8],
        "window_days": days,
        "summary": summary,
        "reason": reason,
        "focus_active": focus_active,
        "detail": (
            "Football-Data.org and API-Football/API-Sports standings can still populate table snapshots and the Tables page "
            "when upcoming fixtures are thin. Scrapers enrich fixtures after they exist, but they are not fixture calendars."
        ),
        "has_any_fixtures": total > 0,
    }


def _dashboard_ops_context(data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Warm-status and API guard banners for the dashboard."""
    global _dashboard_refresh_inflight
    from hibs_predictor.rate_limiter import RateLimiter

    bundle = data or {}
    api_diag = RateLimiter().diagnostics("api_sports")
    warm_in_progress = bool(_dashboard_refresh_inflight)
    cache_stale = bool(bundle.get("cache_stale"))
    cold_start = bool(bundle.get("cold_start"))
    quota_banner: Optional[str] = None
    reason = api_diag.get("block_reason")
    if reason:
        quota_banner = (
            f"API-Sports requests are paused ({reason}). "
            "Fixtures may load from cache; data quality can look lower until the guard resets."
        )
    warm_banner: Optional[str] = None
    if warm_in_progress:
        warm_banner = "Refreshing fixture data in the background — cards may update shortly."
    elif cache_stale and not cold_start:
        warm_banner = "Showing cached fixtures while a background refresh completes."
    return {
        "warm_in_progress": warm_in_progress,
        "cache_stale": cache_stale,
        "quota_banner": quota_banner,
        "warm_banner": warm_banner,
        "api_sports_guard": api_diag,
    }


def _dashboard_info_box(fixture_coverage: Dict[str, Any], total: int) -> Dict[str, Any]:
    """Small user-facing dashboard summary; feed/provider detail belongs on /status."""
    loaded = fixture_coverage.get("loaded") or []
    loaded_names = [str(row.get("name") or row.get("code")) for row in loaded if row]
    return {
        "loaded_count": len(loaded_names),
        "loaded_names": loaded_names,
        "loaded_names_text": ", ".join(loaded_names),
        "total_fixtures": total,
        "description": (
            "hibs-bet turns upcoming fixtures into probability-led match reads: form, odds, table context, "
            "data quality and value signals are combined to help compare bets and spot stronger angles."
        ),
    }


def fetch_all_fixtures(
    *,
    attach_live: bool = False,
    include_domestic: bool = False,
    allow_stale: bool = False,
    force_refresh: bool = False,
    reboost: bool = False,
) -> Dict:
    from hibs_predictor.fixture_statistics_xg import reset_statistics_xg_budget

    try:
        lock_handle = _acquire_fixture_bundle_fetch_lock(blocking=False)
    except BlockingIOError:
        cache = Cache()
        ttl = _cache_ttl_hours(1.0)
        ck = _all_fixtures_cache_key(include_domestic=include_domestic)
        cached = cache.get(ck, ttl_hours=ttl)
        if cached and _is_complete_fixture_bundle(cached):
            bundle = dict(cached)
            bundle["fetch_days"] = _fetch_window_days()
            bundle["cache_stale"] = True
            return bundle
        stale = cache.peek(ck)
        if isinstance(stale, dict) and _is_complete_fixture_bundle(stale) and stale.get("all"):
            bundle = dict(stale)
            bundle["fetch_days"] = _fetch_window_days()
            bundle["cache_stale"] = True
            return bundle
        return _cold_fixture_bundle(include_domestic=include_domestic)

    try:
        return _fetch_all_fixtures_locked(
            attach_live=attach_live,
            include_domestic=include_domestic,
            allow_stale=allow_stale,
            force_refresh=force_refresh,
            reboost=reboost,
        )
    finally:
        _release_fixture_bundle_fetch_lock(lock_handle)


def _fetch_all_fixtures_locked(
    *,
    attach_live: bool = False,
    include_domestic: bool = False,
    allow_stale: bool = False,
    force_refresh: bool = False,
    reboost: bool = False,
) -> Dict:
    from hibs_predictor.fixture_statistics_xg import reset_statistics_xg_budget

    reset_statistics_xg_budget()
    cache = Cache()
    _maybe_prune_cache(cache)
    ttl = _cache_ttl_hours(1.0)
    ck = _all_fixtures_cache_key(include_domestic=include_domestic)
    cached = cache.get(ck, ttl_hours=ttl)
    if cached:
        if _is_complete_fixture_bundle(cached) and _all_fixtures_bundle_fresh(cached):
            bundle = dict(cached)
            bundle["fetch_days"] = _fetch_window_days()
            if attach_live:
                _refresh_live_on_bundle(bundle)
            return bundle
        if allow_stale and not force_refresh and _is_complete_fixture_bundle(cached):
            bundle = dict(cached)
            bundle["fetch_days"] = _fetch_window_days()
            bundle["cache_stale"] = True
            if attach_live:
                _refresh_live_on_bundle(bundle)
            return bundle
        if _is_complete_fixture_bundle(cached):
            _hibs_debug_log(f"partial all_fixtures bundle bust key={ck}")
        all_f = cached.get("all") if isinstance(cached, dict) else None
        if not all_f and isinstance(cached, list):
            all_f = cached
        if all_f:
            bundle = _finalize_fixture_bundle(
                all_f,
                attach_live=attach_live,
                include_domestic=include_domestic,
                reboost=reboost,
            )
            if bundle.get("total"):
                cache.set(ck, bundle, ttl_hours=ttl)
            return bundle
        _hibs_debug_log(f"skip empty all_fixtures cache key={ck}")

    stale_bundle = cache.peek(ck)
    stale_all = (
        stale_bundle.get("all")
        if isinstance(stale_bundle, dict) and _is_complete_fixture_bundle(stale_bundle)
        else None
    )
    if (
        allow_stale
        and not force_refresh
        and isinstance(stale_bundle, dict)
        and _is_complete_fixture_bundle(stale_bundle)
        and stale_bundle.get("all")
    ):
        bundle = dict(stale_bundle)
        bundle["fetch_days"] = _fetch_window_days()
        bundle["cache_stale"] = True
        if attach_live:
            _refresh_live_on_bundle(bundle)
        return bundle

    all_fixtures = _fetch_all_league_fixtures_parallel(
        include_domestic=include_domestic, allow_stale=allow_stale
    )
    if stale_all:
        _merge_stale_all_fixtures_rows(all_fixtures, stale_all)
    result = _finalize_fixture_bundle(
        all_fixtures,
        attach_live=attach_live,
        include_domestic=include_domestic,
        reboost=reboost,
    )
    if stale_all and result.get("all"):
        old_fresh = _bundle_enrich_fresh_count(stale_bundle)
        new_fresh = _bundle_enrich_fresh_count(result)
        if old_fresh > new_fresh:
            bundle = dict(stale_bundle)
            bundle["fetch_days"] = _fetch_window_days()
            bundle["cache_stale"] = True
            if attach_live:
                _refresh_live_on_bundle(bundle)
            _log_resilience(
                "fixture_bundle_keep_stale_cache",
                key=ck,
                old_fresh=old_fresh,
                new_fresh=new_fresh,
            )
            return bundle
    if result.get("total") and _bundle_ok_to_persist(result):
        cache.set(ck, result, ttl_hours=ttl)
    elif result.get("total"):
        _log_resilience(
            "fixture_bundle_skip_thin_cache",
            key=ck,
            fresh=_bundle_enrich_fresh_count(result),
            total=len(result.get("all") or []),
        )
        if stale_all and _bundle_enrich_fresh_count(stale_bundle) > _bundle_enrich_fresh_count(result):
            bundle = dict(stale_bundle)
            bundle["fetch_days"] = _fetch_window_days()
            bundle["cache_stale"] = True
            if attach_live:
                _refresh_live_on_bundle(bundle)
            return bundle
    else:
        _hibs_debug_log(f"not caching empty all_fixtures bundle key={ck}")
        if allow_stale:
            stale = cache.peek(ck)
            if isinstance(stale, dict) and _is_complete_fixture_bundle(stale) and stale.get("all"):
                bundle = dict(stale)
                bundle["fetch_days"] = _fetch_window_days()
                bundle["cache_stale"] = True
                if attach_live:
                    _refresh_live_on_bundle(bundle)
                _log_resilience(
                    "fixture_bundle_stale_fallback",
                    key=ck,
                    total=bundle.get("total"),
                )
                return bundle
    return result


def _fixture_ko_sort_key(fixture: Dict[str, Any]) -> str:
    """Sort key: kick-off datetime (UTC ISO, empty last)."""
    return str(fixture.get("kickoff_sort") or fixture.get("date") or "9999")


def _sidebar_upcoming(all_fixtures: List[Dict[str, Any]], limit: int = 80) -> List[Dict[str, Any]]:
    """Compact upcoming list for the left rail — sorted by model confidence, then kick-off."""
    rows: List[Dict[str, Any]] = []
    for f in all_fixtures:
        fid = f.get("id")
        if fid is None:
            continue
        p = f.get("prediction") if isinstance(f.get("prediction"), dict) else {}
        si = p.get("structured_insight") if isinstance(p.get("structured_insight"), dict) else {}
        conf_raw = p.get("confidence_pct")
        if conf_raw is None:
            conf_raw = si.get("confidence_pct")
        try:
            confidence = float(conf_raw) if conf_raw is not None else 0.0
        except (TypeError, ValueError):
            confidence = 0.0
        rationale = (si.get("rationale_summary") or si.get("pick") or "").strip()
        if len(rationale) > 100:
            rationale = rationale[:97].rstrip() + "…"
        rows.append(
            {
                "id": fid,
                "home": fixture_team_name(f, "home") or f.get("home", "?"),
                "away": fixture_team_name(f, "away") or f.get("away", "?"),
                "league": f.get("league", ""),
                "league_name": f.get("league_name", ""),
                "dashboard_region": f.get("dashboard_region")
                or league_dashboard_region(str(f.get("league") or "")),
                "kickoff_time": f.get("kickoff_time") or "—",
                "kickoff_day_local": f.get("kickoff_day_local") or "",
                "kickoff_sort": f.get("kickoff_sort") or f.get("date") or "",
                "confidence": confidence,
                "rationale_snippet": rationale,
                "pick": si.get("pick") or "",
            }
        )
    rows.sort(
        key=lambda r: (
            -(r.get("confidence") or 0),
            str(r.get("kickoff_sort") or "9999"),
        )
    )
    return rows[:limit]


def _players_fixture_sort_key(fixture: Dict[str, Any]) -> Tuple[int, str]:
    from hibs_predictor.config import players_panel_league_code, players_panel_league_order_index

    order = players_panel_league_order_index()
    league_code = players_panel_league_code(str(fixture.get("league") or ""))
    kickoff = str(fixture.get("kickoff_sort") or fixture.get("date") or "9999")
    return (order.get(league_code, 9999), kickoff)


def _sort_fixtures_for_players_panel(all_fixtures: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(all_fixtures or [], key=_players_fixture_sort_key)


def _sky_players_panel(all_fixtures: List[Dict[str, Any]], limit: int = 8) -> List[Dict[str, Any]]:
    """Small player-focused panel for the right dock using existing enriched fixture fields."""
    rows: List[Dict[str, Any]] = []
    for f in _sort_fixtures_for_players_panel(all_fixtures):
        if len(rows) >= int(limit):
            break
        home = fixture_team_name(f, "home") or str(f.get("home") or "?")
        away = fixture_team_name(f, "away") or str(f.get("away") or "?")
        injuries = f.get("fixture_injuries") if isinstance(f.get("fixture_injuries"), list) else []
        hs = f.get("home_top_scorers") if isinstance(f.get("home_top_scorers"), list) else []
        aws = f.get("away_top_scorers") if isinstance(f.get("away_top_scorers"), list) else []
        home_star = ""
        away_star = ""
        if hs:
            top = hs[0] if isinstance(hs[0], dict) else {}
            home_star = str(top.get("name") or "")
        if aws:
            top = aws[0] if isinstance(aws[0], dict) else {}
            away_star = str(top.get("name") or "")
        rows.append(
            {
                "match": f"{home} v {away}",
                "kickoff_time": str(f.get("kickoff_time") or "—"),
                "lineup_confirmed": bool(f.get("lineup_confirmed")),
                "injury_count": len(injuries),
                "home_star": home_star,
                "away_star": away_star,
                "home_recent_n": _safe_int_value(f.get("home_recent_n"), 0),
                "away_recent_n": _safe_int_value(f.get("away_recent_n"), 0),
            }
        )
    return rows


def _player_row_from_fixture(f: Dict[str, Any]) -> Dict[str, Any]:
    from hibs_predictor.config import players_panel_league_code

    home = fixture_team_name(f, "home") or str(f.get("home") or "?")
    away = fixture_team_name(f, "away") or str(f.get("away") or "?")
    lineup_meta = f.get("lineup_meta") if isinstance(f.get("lineup_meta"), dict) else {}
    home_abs = lineup_meta.get("home_scorers_out_of_xi")
    away_abs = lineup_meta.get("away_scorers_out_of_xi")
    home_abs = home_abs if isinstance(home_abs, list) else []
    away_abs = away_abs if isinstance(away_abs, list) else []
    injuries = f.get("fixture_injuries") if isinstance(f.get("fixture_injuries"), list) else []
    league_code = players_panel_league_code(str(f.get("league") or ""))
    return {
        "id": f.get("id"),
        "home": home,
        "away": away,
        "kickoff_time": str(f.get("kickoff_time") or "—"),
        "kickoff_day_local": str(f.get("kickoff_day_local") or ""),
        "league": league_code,
        "league_name": str(f.get("league_name") or LEAGUES.get(league_code, {}).get("name") or league_code),
        "lineup_confirmed": bool(f.get("lineup_confirmed")),
        "home_top_scorers": f.get("home_top_scorers") if isinstance(f.get("home_top_scorers"), list) else [],
        "away_top_scorers": f.get("away_top_scorers") if isinstance(f.get("away_top_scorers"), list) else [],
        "home_scorers_out_of_xi": home_abs,
        "away_scorers_out_of_xi": away_abs,
        "injury_count": len(injuries),
        "home_recent_n": _safe_int_value(f.get("home_recent_n"), 0),
        "away_recent_n": _safe_int_value(f.get("away_recent_n"), 0),
    }


def _players_page_rows(all_fixtures: List[Dict[str, Any]], limit: int = 120) -> List[Dict[str, Any]]:
    """Build richer player-focused rows from existing fixture enrichment."""
    rows: List[Dict[str, Any]] = []
    for f in _sort_fixtures_for_players_panel(all_fixtures):
        if len(rows) >= int(limit):
            break
        rows.append(_player_row_from_fixture(f))
    return rows


def _players_page_groups(
    all_fixtures: List[Dict[str, Any]], limit: int = 120
) -> List[Dict[str, Any]]:
    """League-section groups for players UI (EPL → SPL → Europe → lower tiers)."""
    rows = _players_page_rows(all_fixtures, limit=limit)
    groups: List[Dict[str, Any]] = []
    for row in rows:
        league_code = str(row.get("league") or "")
        if groups and groups[-1].get("league") == league_code:
            groups[-1]["rows"].append(row)
            continue
        groups.append(
            {
                "league": league_code,
                "section_title": row.get("league_name") or LEAGUES.get(league_code, {}).get("name", league_code),
                "rows": [row],
            }
        )
    return groups


def _fixtures_from_dashboard_bundle(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Fixture rows aligned with rendered dashboard day/league blocks (not a stale ``upcoming`` key)."""
    out: List[Dict[str, Any]] = []
    for day in data.get("dashboard_days") or []:
        if not isinstance(day, dict):
            continue
        for lg in day.get("leagues") or []:
            if not isinstance(lg, dict):
                continue
            for fx in lg.get("fixtures") or []:
                if isinstance(fx, dict):
                    out.append(fx)
    if out:
        return out
    return _bundle_fixtures(data)


def _players_groups_for_ui_data(
    data: Dict[str, Any],
    *,
    limit: int = 120,
    include_domestic: bool = False,
) -> List[Dict[str, Any]]:
    """Players panel/page groups; fall back to on-disk bundle when HTML is a cold shell."""
    fixtures = _fixtures_from_dashboard_bundle(data)
    if not fixtures and (data.get("cold_start") or data.get("cache_stale")):
        disk = Cache().peek(_all_fixtures_cache_key(include_domestic=include_domestic))
        if isinstance(disk, dict) and disk.get("all"):
            fixtures = _fixtures_from_dashboard_bundle(disk)
    return _players_page_groups(fixtures, limit=limit)


def _league_block_display_name(league_code: str, fixtures: List[Dict[str, Any]]) -> str:
    """Section heading: shared per-fixture league_name when uniform, else configured league label."""
    names = [(f.get("league_name") or "").strip() for f in fixtures]
    names = [n for n in names if n]
    if len(set(names)) == 1:
        return names[0]
    return LEAGUES.get(league_code, {}).get("name", league_code)


def _dashboard_days_groups(
    all_fixtures: List[Dict[str, Any]],
    *,
    include_domestic: bool = False,
) -> List[Dict[str, Any]]:
    """Group fixtures by local calendar day, leagues in DASHBOARD_LEAGUE_ORDER, each league by KO time."""
    from collections import defaultdict
    from hibs_predictor.display_tz import day_heading_for_local_date, local_today

    by_day: Dict[str, Dict[str, List[Dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for f in all_fixtures:
        day_iso = (f.get("kickoff_day_local") or "").strip()
        if not day_iso:
            raw = f.get("date") or ""
            if len(raw) < 10:
                continue
            day_iso = raw[:10]
        lc = f.get("league") or ""
        if lc:
            by_day[day_iso][lc].append(f)
    today_local = local_today()
    order_index = {c: i for i, c in enumerate(_dashboard_league_order(include_domestic=include_domestic))}
    out: List[Dict[str, Any]] = []
    for day_iso in sorted(by_day.keys()):
        leagues_block: List[Dict[str, Any]] = []
        seen_lc = set()

        def _append_league(lc: str) -> None:
            fl = by_day[day_iso].get(lc, [])
            if not fl:
                return
            fl.sort(key=_fixture_ko_sort_key)
            leagues_block.append(
                {
                    "code": lc,
                    "name": _league_block_display_name(lc, fl),
                    "fixtures": fl,
                }
            )
            seen_lc.add(lc)

        for lc in _dashboard_league_order(include_domestic=include_domestic):
            _append_league(lc)
        for lc in sorted(by_day[day_iso].keys(), key=lambda c: (order_index.get(c, 999), c)):
            if lc not in seen_lc and by_day[day_iso][lc]:
                _append_league(lc)
        if not leagues_block:
            continue
        day_count = sum(len(lb["fixtures"]) for lb in leagues_block)
        heading = day_heading_for_local_date(day_iso, day_count, today_local)
        out.append({"date_iso": day_iso, "heading": heading, "fixture_count": day_count, "leagues": leagues_block})
    return out


def _leagues_for_filter(by_league: Dict[str, List], *, include_domestic: bool = False) -> List[tuple]:
    """League filter chips in dashboard order — competitions with fixtures, plus summer focus list."""
    from hibs_predictor.tournament_focus import (
        active_competition_league_codes,
        domestic_offseason_active,
        friendlies_window_active,
        post_wc_domestic_european_active,
        tournament_focus_active,
    )

    order_index = {c: i for i, c in enumerate(_dashboard_league_order(include_domestic=include_domestic))}
    min_n = _min_league_chip_fixtures()
    codes: List[str] = []
    seen: set = set()
    focus_codes: set[str] = set()
    # Summer / pre- & post-WC: show WC, friendlies, Nordics, cup finals even when count is 0.
    summer_chips = not include_domestic and (
        tournament_focus_active()
        or domestic_offseason_active()
        or friendlies_window_active()
        or post_wc_domestic_european_active()
    )
    if summer_chips:
        focus_codes = set(active_competition_league_codes())
        for c in focus_codes:
            if c in LEAGUES and c not in seen:
                codes.append(c)
                seen.add(c)
    for c in _dashboard_league_order(include_domestic=include_domestic):
        if c in LEAGUES and len(by_league.get(c) or []) >= min_n:
            if c not in seen:
                codes.append(c)
                seen.add(c)
    for c in sorted(by_league.keys(), key=lambda x: (order_index.get(x, 999), x)):
        if c in LEAGUES and c not in seen and len(by_league.get(c) or []) >= min_n:
            codes.append(c)
            seen.add(c)

    def _chip_label(code: str) -> str:
        n = len(by_league.get(code) or [])
        base = _league_block_display_name(code, by_league.get(code) or [])
        if n == 0 and code in focus_codes:
            return f"{base} (0)"
        return base

    return [(c, _chip_label(c)) for c in codes]


def _assistant_packets_from_fixtures(fixtures: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    from hibs_predictor.assistant_context import enrich_assistant_packet
    from hibs_predictor.match_insight import build_assistant_packet
    from hibs_predictor.tournament_focus import prioritize_fixtures_for_focus

    ordered = prioritize_fixtures_for_focus(fixtures)
    return [enrich_assistant_packet(build_assistant_packet(f)) for f in ordered]


def _assistant_bundle(fixtures: List[Dict[str, Any]]) -> Dict[str, Any]:
    from hibs_predictor.assistant_context import build_acca_candidates, build_fixtures_summary
    from hibs_predictor.assistant_recommendations import build_assistant_recommendations

    packets = _assistant_packets_from_fixtures(fixtures)
    return {
        "packets": packets,
        "fixtures_summary": build_fixtures_summary(packets, max_n=80),
        "recommendations": build_assistant_recommendations(packets),
        "acca_candidates": build_acca_candidates(packets),
        "count": len(packets),
    }


_assistant_bundle_cache: Dict[str, Any] = {"key": "", "t": 0.0, "bundle": None}
_assistant_bundle_cache_lock = threading.Lock()


def _assistant_bundle_cache_ttl_sec() -> float:
    try:
        return max(30.0, float(os.getenv("HIBS_ASSISTANT_CACHE_SEC", "120")))
    except ValueError:
        return 120.0


def _cached_assistant_bundle(
    *,
    attach_live: bool = False,
    allow_stale: bool = True,
    include_domestic: bool = False,
) -> Dict[str, Any]:
    """Reuse a short-lived assistant bundle so chat/snapshot do not block on full refetch each request."""
    cache_key = f"a:{int(attach_live)}:s:{int(allow_stale)}:d:{int(include_domestic)}"
    now = _time.monotonic()
    ttl = _assistant_bundle_cache_ttl_sec()
    with _assistant_bundle_cache_lock:
        hit = _assistant_bundle_cache.get("bundle")
        if (
            hit
            and _assistant_bundle_cache.get("key") == cache_key
            and (now - float(_assistant_bundle_cache.get("t") or 0)) < ttl
        ):
            return hit

    data = _load_fixtures_for_http(
        attach_live=attach_live,
        include_domestic=include_domestic,
    )
    bundle = _assistant_bundle(_bundle_fixtures(data))
    with _assistant_bundle_cache_lock:
        _assistant_bundle_cache["key"] = cache_key
        _assistant_bundle_cache["t"] = now
        _assistant_bundle_cache["bundle"] = bundle
    return bundle


def _cold_fixture_bundle(include_domestic: bool) -> Dict[str, Any]:
    """Non-blocking empty fixture bundle while background warm runs."""
    data = _finalize_fixture_bundle([], include_domestic=include_domestic)
    data["cache_stale"] = True
    data["cold_start"] = True
    return data


def _stale_fixture_bundle_for_refresh(*, include_domestic: bool) -> Optional[Dict[str, Any]]:
    """Last on-disk bundle kept in memory after refresh=1 clears caches (avoids blank dashboard)."""
    ck = _all_fixtures_cache_key(include_domestic=include_domestic)
    disk = Cache().peek(ck)
    if (
        (not isinstance(disk, dict) or not _is_complete_fixture_bundle(disk) or not disk.get("all"))
        and include_domestic
    ):
        # All-leagues view: keep intl/summer bundle visible while the full 35-league rebuild runs.
        disk = Cache().peek(_all_fixtures_cache_key(include_domestic=False))
    if not isinstance(disk, dict) or not _is_complete_fixture_bundle(disk) or not disk.get("all"):
        return None
    bundle = dict(disk)
    bundle["fetch_days"] = _fetch_window_days()
    bundle["cache_stale"] = True
    bundle.pop("cold_start", None)
    return bundle


def clear_assistant_bundle_cache() -> None:
    with _assistant_bundle_cache_lock:
        _assistant_bundle_cache["bundle"] = None
        _assistant_bundle_cache["t"] = 0.0
        _assistant_bundle_cache["key"] = ""


def _affiliate_routing_key() -> str:
    sid = ""
    try:
        sid = str(getattr(g, "session_id", "") or "")
    except Exception:
        pass
    if not sid and has_request_context():
        from flask import session

        sid = str(session.get("_id") or "")
    ip = (request.headers.get("X-Forwarded-For") or request.remote_addr or "").split(",")[0].strip()
    ua = request.headers.get("User-Agent") or ""
    return hashlib.sha256(f"{sid}|{ip}|{ua}".encode("utf-8")).hexdigest()


def _affiliate_click_context(overrides: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    ctx = {
        "sport": (request.args.get("sport") or "football").strip()[:32],
        "fixture_id": (request.args.get("fixture_id") or "").strip()[:64],
        "outcome": (request.args.get("outcome") or "").strip()[:32],
        "market": (request.args.get("market") or "1x2").strip()[:32],
        "source": (request.args.get("source") or "redirect").strip()[:64],
    }
    if overrides:
        ctx.update({k: v for k, v in overrides.items() if v is not None})
    return ctx


def _affiliate_redirect_response(bookmaker: str, *, ctx_override: Optional[Dict[str, str]] = None) -> Any:
    from hibs_predictor.affiliate_clicks import log_click
    from hibs_predictor.affiliate_config import (
        affiliate_enabled,
        build_outbound_affiliate_url,
        resolve_tracking_route,
    )

    if not affiliate_enabled():
        abort(404)
    ctx = _affiliate_click_context(ctx_override)
    routing_key = _affiliate_routing_key()
    if ctx.get("fixture_id"):
        routing_key = f"{routing_key}|{ctx['fixture_id']}|{ctx.get('outcome') or ''}"
    try:
        tracking_id, route_target, network_key = resolve_tracking_route(bookmaker, routing_key)
        outbound = build_outbound_affiliate_url(
            bookmaker,
            routing_key=routing_key,
            sport=ctx.get("sport"),
            fixture_id=ctx.get("fixture_id") or None,
            outcome=ctx.get("outcome") or None,
            market=ctx.get("market"),
            source=ctx.get("source"),
        )
    except ValueError:
        abort(404)
    ip = (request.headers.get("X-Forwarded-For") or request.remote_addr or "").split(",")[0].strip()
    ip_hash = hashlib.sha256(ip.encode("utf-8")).hexdigest()[:16] if ip else None
    try:
        log_click(
            bookmaker=network_key,
            route_target=route_target,
            tracking_id=tracking_id,
            sport=ctx.get("sport"),
            fixture_id=ctx.get("fixture_id") or None,
            outcome=ctx.get("outcome") or None,
            market=ctx.get("market"),
            source=ctx.get("source"),
            routing_key=routing_key,
            user_agent=(request.headers.get("User-Agent") or "")[:256],
            ip_hash=ip_hash,
        )
    except Exception as exc:
        log.warning("affiliate click log failed: %s", exc)
    return redirect(outbound, code=302)


@app.route("/go/<bookmaker>")
def affiliate_go_bookmaker(bookmaker: str):
    """Tracked redirect to configured bookmaker (Structure B revenue-share routing)."""
    return _affiliate_redirect_response(bookmaker)


@app.route("/go/betslip")
def affiliate_go_betslip():
    """Tracked redirect for acca / WhatsApp slip deep-links."""
    bm = request.args.get("bookmaker") or ""
    if not bm:
        from hibs_predictor.affiliate_config import load_affiliate_config, normalize_bookmaker_key

        cfg = load_affiliate_config()
        bm = normalize_bookmaker_key(str(cfg.get("default_bookmaker") or "")) or "bet365"
    return _affiliate_redirect_response(
        bm,
        ctx_override={
            "source": (request.args.get("source") or "betslip").strip()[:64],
            "market": (request.args.get("market") or "acca").strip()[:32],
        },
    )


@app.route("/api/place-bet", methods=["POST"])
@login_required
def api_place_bet():
    """Return server-side tracked redirect URL for betslip placement (buyer swaps tracking IDs in config)."""
    from hibs_predictor.affiliate_config import affiliate_enabled, load_affiliate_config, normalize_bookmaker_key

    if not affiliate_enabled():
        return jsonify({"ok": False, "error": "affiliate_disabled"}), 503
    body = request.get_json(silent=True) or {}
    bm = normalize_bookmaker_key(str(body.get("bookmaker") or "")) or normalize_bookmaker_key(
        str(load_affiliate_config().get("default_bookmaker") or "")
    )
    if not bm:
        return jsonify({"ok": False, "error": "unknown_bookmaker"}), 400
    selections = body.get("selections") or []
    fixture_id = ""
    outcome = ""
    if selections and isinstance(selections[0], dict):
        fixture_id = str(selections[0].get("fixture_id") or selections[0].get("fid") or "")
        outcome = str(selections[0].get("outcome") or "")
    q = urlencode(
        {
            "bookmaker": bm,
            "source": "place_bet_api",
            "sport": str(body.get("sport") or "football"),
            "fixture_id": fixture_id,
            "outcome": outcome,
            "legs": str(len(selections)),
        }
    )
    redirect_path = f"/go/betslip?{q}"
    cfg = load_affiliate_config()
    return jsonify(
        {
            "ok": True,
            "redirect_url": redirect_path,
            "affiliate_url": request.host_url.rstrip("/") + redirect_path,
            "bookmaker": bm,
            "revenue_share_clause_enabled": bool(cfg.get("revenue_share_clause_enabled")),
            "master_revenue_share_pct": int(cfg.get("master_revenue_share_pct") or 20),
        }
    )


@app.route("/api/affiliate/summary")
@login_required
def api_affiliate_summary():
    from hibs_predictor.affiliate_clicks import click_summary
    from hibs_predictor.affiliate_config import load_affiliate_config, public_affiliate_context

    cfg = load_affiliate_config()
    summary = click_summary()
    summary["config"] = public_affiliate_context()
    summary["revenue_share_clause_enabled"] = bool(cfg.get("revenue_share_clause_enabled"))
    summary["master_revenue_share_pct"] = int(cfg.get("master_revenue_share_pct") or 20)
    return jsonify(summary)


@app.route("/api/ping")
def api_ping():
    """Fast readiness probe for local launchers (no auth, no external I/O)."""
    from hibs_predictor.deploy_info import gather_deploy_info

    payload = {"ok": True}
    payload.update(gather_deploy_info())
    return jsonify(payload)


@app.route("/login", methods=["GET", "POST"])
def login():
    if not auth_enabled():
        return redirect(url_for("index"))
    if is_logged_in():
        return redirect(safe_next_url(request.args.get("next")))
    next_url = safe_next_url(request.form.get("next") or request.args.get("next"))
    error = None
    if request.method == "POST":
        if check_password(request.form.get("password", "")):
            login_user()
            return redirect(next_url)
        error = "Incorrect password."
    return render_template("login.html", error=error, next_url=next_url)


@app.route("/logout", methods=["GET", "POST"])
def logout():
    logout_user()
    if auth_enabled():
        return redirect(url_for("login"))
    return redirect(url_for("index"))


def _dashboard_logged_results() -> Dict[str, Any]:
    from hibs_predictor.prediction_log import recent_logged_results_dict

    return recent_logged_results_dict(limit=10)


@app.route("/")
@login_required
def index():
    include_domestic = request.args.get("domestic") == "1"
    force_refresh = request.args.get("refresh") == "1"
    refresh_stale_bundle: Optional[Dict[str, Any]] = None
    if force_refresh:
        refresh_stale_bundle = _stale_fixture_bundle_for_refresh(include_domestic=include_domestic)
        clear_application_caches(
            all_disk=request.args.get("all") == "1",
            reset_rate_limits=False,
        )
    elif not include_domestic:
        cached_page = _dashboard_page_cache_get(allow_stale=True)
        if cached_page is not None:
            body, etag = cached_page
            if request.headers.get("If-None-Match") == etag:
                resp = make_response("", 304)
            else:
                resp = make_response(body)
            resp.mimetype = "text/html; charset=utf-8"
            resp.headers["ETag"] = etag
            resp.headers["Cache-Control"] = "private, max-age=30"
            _schedule_dashboard_refresh()
            return _set_fetch_days_cookie_if_requested(resp)

    # Never block the HTML dashboard on a full refetch after Refresh (avoids nginx 502/500).
    progressive = _progressive_load_enabled()
    if force_refresh:
        _schedule_dashboard_refresh()
        if refresh_stale_bundle is not None:
            data = refresh_stale_bundle
        else:
            data = _cold_fixture_bundle(include_domestic=include_domestic)
        upcoming = _bundle_fixtures(data)
        recent_results = {"all": [], "days": [], "total": 0, "results_days": 3}
        if _defer_assistant_on_page():
            assistant_packets = []
            assistant_bundle = {"packets": [], "recommendations": [], "acca_candidates": [], "count": 0}
        else:
            assistant_bundle = _assistant_bundle(upcoming)
            assistant_packets = assistant_bundle["packets"]
        fixture_coverage = data.get("fixture_coverage", {})
        html = render_template(
            "dashboard.html",
            all_fixtures=upcoming,
            by_region=data["by_region"],
            by_league=data["by_league"],
            dashboard_days=data["dashboard_days"],
            value_bets=data["value_bets"],
            total=data["total"],
            value_bet_count=data["value_bet_count"],
            fixture_coverage=fixture_coverage,
            dashboard_info=_dashboard_info_box(fixture_coverage, data["total"]),
            league_regions=LEAGUE_REGIONS,
            dashboard_filter_regions=DASHBOARD_FILTER_REGIONS,
            leagues_for_filter=_leagues_for_filter(data["by_league"], include_domestic=include_domestic),
            min_league_chip_fixtures=_min_league_chip_fixtures(),
            dashboard_league_order=_dashboard_league_order(include_domestic=include_domestic),
            tournament_focus=_tournament_focus_context(include_domestic=include_domestic),
            include_domestic=include_domestic,
            fetch_days=_fetch_window_days(),
            has_api_clients=data.get(
                "has_api_clients",
                ("api_sports" in aggregator.clients or "football_data_org" in aggregator.clients),
            ),
            leagues=LEAGUES,
            data_quality_ui_min=_ui_data_quality_min_pct(),
            data_quality_show_90_chip=_ui_show_dq90_chip(),
            assistant_packets=assistant_packets,
            assistant_recommendations=assistant_bundle.get("recommendations"),
            sidebar_upcoming=data.get("sidebar_upcoming", []),
            players_dock_groups=_players_groups_for_ui_data(
                data, limit=12, include_domestic=include_domestic
            ),
            players_dock_cold_start=bool(data.get("cold_start") or data.get("cache_stale")),
            recent_results=recent_results.get("all", []),
            recent_results_days=recent_results.get("results_days", 3),
            recent_results_total=recent_results.get("total", 0),
            recent_results_days_groups=recent_results.get("days", []),
            display_tz_label=display_tz_label(),
            progressive_load=progressive,
            cold_start=bool(data.get("cold_start")),
            ops_banner=_dashboard_ops_context(data),
            logged_results=_dashboard_logged_results(),
        )
        body = html.encode("utf-8")
        resp = make_response(body)
        resp.mimetype = "text/html; charset=utf-8"
        if bool(data.get("cold_start")):
            # Do not cache a cold shell; otherwise clients can loop on refresh=meta reload.
            resp.headers["Cache-Control"] = "no-store, private"
        else:
            etag = _dashboard_page_cache_set(body)
            resp.headers["ETag"] = etag
            resp.headers["Cache-Control"] = "private, max-age=30"
        return _set_fetch_days_cookie_if_requested(resp)

    ck = _all_fixtures_cache_key(include_domestic=include_domestic)
    if progressive and request.args.get("refresh") != "1":
        data = _load_fixtures_for_http(include_domestic=include_domestic)
    else:
        data = fetch_all_fixtures(
            attach_live=False,
            include_domestic=include_domestic,
            allow_stale=True,
        )
    if data.get("cache_stale"):
        _schedule_dashboard_refresh()
    upcoming = _bundle_fixtures(data)
    try:
        _refresh_live_kickoff_window(upcoming)
    except Exception as exc:
        print(f"[Dashboard live snapshot] {exc!r}")
    from hibs_predictor.recent_results import fetch_recent_results

    if progressive:
        recent_results = {"all": [], "days": [], "total": 0, "results_days": 3}
    else:
        recent_results = fetch_recent_results(aggregator, include_domestic=include_domestic)
    if _defer_assistant_on_page():
        assistant_packets: List[Dict[str, Any]] = []
        assistant_bundle: Dict[str, Any] = {"packets": [], "recommendations": [], "acca_candidates": [], "count": 0}
    else:
        assistant_bundle = _assistant_bundle(upcoming)
        assistant_packets = assistant_bundle["packets"]
    fixture_coverage = data.get("fixture_coverage", {})
    html = render_template(
        "dashboard.html",
        all_fixtures=upcoming,
        by_region=data["by_region"],
        by_league=data["by_league"],
        dashboard_days=data["dashboard_days"],
        value_bets=data["value_bets"],
        total=data["total"],
        value_bet_count=data["value_bet_count"],
        fixture_coverage=fixture_coverage,
        dashboard_info=_dashboard_info_box(fixture_coverage, data["total"]),
        league_regions=LEAGUE_REGIONS,
        dashboard_filter_regions=DASHBOARD_FILTER_REGIONS,
        leagues_for_filter=_leagues_for_filter(data["by_league"], include_domestic=include_domestic),
        min_league_chip_fixtures=_min_league_chip_fixtures(),
        dashboard_league_order=_dashboard_league_order(include_domestic=include_domestic),
        tournament_focus=_tournament_focus_context(include_domestic=include_domestic),
        include_domestic=include_domestic,
        fetch_days=_fetch_window_days(),
        has_api_clients=data.get(
            "has_api_clients",
            ("api_sports" in aggregator.clients or "football_data_org" in aggregator.clients),
        ),
        leagues=LEAGUES,
        data_quality_ui_min=_ui_data_quality_min_pct(),
        data_quality_show_90_chip=_ui_show_dq90_chip(),
        assistant_packets=assistant_packets,
        assistant_recommendations=assistant_bundle.get("recommendations"),
        sidebar_upcoming=data.get("sidebar_upcoming", []),
        players_dock_groups=_players_groups_for_ui_data(
            data, limit=12, include_domestic=include_domestic
        ),
        players_dock_cold_start=bool(data.get("cold_start") or data.get("cache_stale")),
        recent_results=recent_results.get("all", []),
        recent_results_days=recent_results.get("results_days", 3),
        recent_results_total=recent_results.get("total", 0),
        recent_results_days_groups=recent_results.get("days", []),
        display_tz_label=display_tz_label(),
        progressive_load=progressive,
        cold_start=bool(data.get("cold_start")),
        ops_banner=_dashboard_ops_context(data),
        logged_results=_dashboard_logged_results(),
    )
    body = html.encode("utf-8")
    resp = make_response(body)
    resp.mimetype = "text/html; charset=utf-8"
    if bool(data.get("cold_start")):
        # Avoid persisting a temporary loading shell in the page cache.
        resp.headers["Cache-Control"] = "no-store, private"
    else:
        etag = _dashboard_page_cache_set(body)
        resp.headers["ETag"] = etag
        resp.headers["Cache-Control"] = "private, max-age=30"
    return _set_fetch_days_cookie_if_requested(resp)


@app.route("/api/assistant/snapshot")
@login_required
def api_assistant_snapshot():
    """Structured insight packets + acca/market recommendations for the Betting Assistant."""
    include_domestic = request.args.get("domestic") == "1"
    bundle = _cached_assistant_bundle(
        attach_live=True,
        allow_stale=True,
        include_domestic=include_domestic,
    )
    return jsonify(bundle)


@app.route("/api/assistant/recommendations")
@login_required
def api_assistant_recommendations():
    """Acca and market recommendations only (packets omitted for lighter payload)."""
    bundle = _cached_assistant_bundle(attach_live=False, allow_stale=True)
    return jsonify(
        {
            "recommendations": bundle.get("recommendations"),
            "count": bundle.get("count", 0),
        }
    )


@app.route("/api/assistant/chat", methods=["POST"])
@login_required
def api_assistant_chat():
    """Natural-language assistant: stats, accas, best bets (data-gated)."""
    from hibs_predictor.assistant_chat import handle_chat

    payload = request.get_json(silent=True) or {}
    question = (payload.get("question") or payload.get("q") or "").strip()
    if not question:
        return jsonify({"error": "question required"}), 400
    fixture_id = payload.get("fixture_id")
    q_lower = question.lower()
    want_live = "live" in q_lower or "in play" in q_lower or "in-play" in q_lower
    bundle = _cached_assistant_bundle(attach_live=want_live, allow_stale=True)
    legs = payload.get("legs")
    if legs is not None and not isinstance(legs, list):
        legs = None
    reply = handle_chat(
        question,
        bundle.get("packets") or [],
        recommendations=bundle.get("recommendations"),
        fixture_id=fixture_id,
        legs=legs,
    )
    return jsonify(reply)


@app.route("/api/assistant/acca-review", methods=["POST"])
@login_required
def api_assistant_acca_review():
    """Structured leg-by-leg review for acca / betslip selections."""
    from hibs_predictor.acca_review import review_acca_legs

    payload = request.get_json(silent=True) or {}
    legs = payload.get("legs")
    if not isinstance(legs, list) or not legs:
        return jsonify({"error": "legs array required"}), 400
    bundle = _cached_assistant_bundle(attach_live=False, allow_stale=True)
    packets = bundle.get("packets") or []
    return jsonify(review_acca_legs(legs, packets))


def _audit_api_token_ok() -> bool:
    import secrets

    tok = (os.getenv("HIBS_AUDIT_API_TOKEN") or "").strip()
    if not tok:
        return False
    auth = (request.headers.get("Authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        if secrets.compare_digest(auth[7:].strip(), tok):
            return True
    hdr = (request.headers.get("X-HIBS-Audit-Token") or "").strip()
    if hdr and secrets.compare_digest(hdr, tok):
        return True
    return secrets.compare_digest(request.args.get("token", ""), tok)


@app.route("/api/audit/summary")
@login_required
def api_audit_summary():
    """Calibration / audit metrics from the prediction log SQLite (optional)."""
    if not _audit_api_token_ok():
        abort(404)
    from hibs_predictor.prediction_log import report_summary_dict

    return jsonify(report_summary_dict())


@app.route("/api/monitor/summary")
@login_required
def api_monitor_summary():
    """Rolling-window prediction vs outcome metrics (HIBS_MONITOR_DAYS, default 28)."""
    from hibs_predictor.prediction_log import monitor_summary_dict

    days_arg = request.args.get("days")
    days: Optional[int] = None
    if days_arg:
        try:
            days = max(1, min(365, int(days_arg)))
        except ValueError:
            return jsonify({"ok": False, "error": "invalid_days"}), 400
    return jsonify(monitor_summary_dict(days=days))


@app.route("/api/monitor/sync-results", methods=["POST"])
@login_required
def api_monitor_sync_results():
    """Join FT scores to logged snapshots (engine monitor / pred-log-sync)."""
    from hibs_predictor.prediction_log import run_pred_log_sync_for_web

    min_h = request.args.get("min_hours")
    min_after: Optional[float] = None
    if min_h is not None:
        try:
            min_after = max(0.0, float(min_h))
        except ValueError:
            return jsonify({"ok": False, "error": "invalid_min_hours"}), 400
    body = request.get_json(silent=True) if request.is_json else {}
    force = isinstance(body, dict) and body.get("force")
    if force and min_after is None:
        min_after = 0.0
    payload = run_pred_log_sync_for_web(min_after_kickoff_hours=min_after)
    status = 200 if payload.get("ok") else 400
    return jsonify(payload), status


@app.route("/api/monitor/recent-results")
@login_required
def api_monitor_recent_results():
    """Latest settled rows from prediction audit log (engine monitor)."""
    from hibs_predictor.prediction_log import recent_logged_results_dict

    try:
        limit = max(1, min(50, int(request.args.get("limit", "12"))))
    except ValueError:
        return jsonify({"ok": False, "error": "invalid_limit"}), 400
    return jsonify(recent_logged_results_dict(limit=limit))


@app.route("/api/cache/clear", methods=["POST", "GET"])
@login_required
def api_cache_clear():
    """Clear fixture disk cache and in-memory /api/health cache. GET is for local dev only."""
    if request.method == "GET" and (os.getenv("HIBS_PRODUCTION") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return jsonify({"error": "get_not_allowed_in_production"}), 405
    all_disk = request.args.get("all") == "1"
    if request.method == "POST" and request.is_json:
        body = request.get_json(silent=True) or {}
        if isinstance(body, dict) and body.get("all"):
            all_disk = True
    cleared = clear_application_caches(all_disk=all_disk)
    return jsonify({"cleared": cleared, "all_disk": all_disk})


@app.route("/harvested-execution")
@login_required(allow_public_health=True)
def harvested_execution_status_page():
    """Harvested Execution ops dashboard (paper/shadow metrics)."""
    from hibs_predictor.hibs_brand import hibs_brand_context
    from hibs_predictor.product_links import infer_football_nav_active, infer_product_active, product_bar_context
    from hibs_predictor.trading_status import trading_metrics_base_url

    ctx = hibs_brand_context()
    ctx.update(product_bar_context(active="trading"))
    ctx["metrics_url"] = trading_metrics_base_url()
    return render_template("harvested_execution_status.html", **ctx)


@app.route("/api/trading/status")
@login_required(allow_public_health=True)
def api_trading_status():
    from hibs_predictor.trading_status import fetch_trading_status

    return jsonify(fetch_trading_status())


_SCRAPER_CATALOG_CACHE: Dict[str, Any] = {"payload": None}


@app.route("/api/scrapers/catalog")
@login_required(allow_public_health=True)
def api_scrapers_catalog():
    """Static field-ladder catalog — zero network I/O (cached in-process)."""
    if _SCRAPER_CATALOG_CACHE["payload"] is None:
        from hibs_predictor.scrapers.multi_scraper_api import catalog_summary

        _SCRAPER_CATALOG_CACHE["payload"] = catalog_summary()
    return jsonify(_SCRAPER_CATALOG_CACHE["payload"])


_SCRAPE_STATUS_CACHE: Dict[str, Any] = {"payload": None}


@app.route("/api/scrape/status")
@login_required(allow_public_health=True)
def api_scrape_status():
    """Scrape-first mode + wired source catalog (no network I/O)."""
    if _SCRAPE_STATUS_CACHE["payload"] is None:
        from hibs_predictor.scrapers.low_source_api import scrape_status_payload

        _SCRAPE_STATUS_CACHE["payload"] = scrape_status_payload()
    return jsonify(_SCRAPE_STATUS_CACHE["payload"])


@app.route("/api/scrape/fixtures")
@login_required(allow_public_health=True)
def api_scrape_fixtures():
    """Scrape-only fixtures (FDO → FotMob → ESPN). Optional enrich + thin-data rescue."""
    from hibs_predictor.scrapers.low_source_api import list_fixtures_payload

    league_code = (request.args.get("league") or "EPL").strip().upper()
    enrich = request.args.get("enrich", "0") == "1"
    rescue = request.args.get("rescue", "0") == "1"
    return jsonify(
        list_fixtures_payload(
            league_code,
            aggregator,
            enrich=enrich,
            rescue=rescue,
        )
    )


@app.route("/api/scrape/fixture/<path:fixture_key>")
@login_required(allow_public_health=True)
def api_scrape_fixture(fixture_key: str):
    """Per-fixture low-source enrichment via scraper ladders (``?rescue=1`` forces thin rescue)."""
    from hibs_predictor.scrapers.low_source_api import resolve_fixture_low_source

    league_code = (request.args.get("league") or "EPL").strip().upper()
    rescue = request.args.get("rescue", "0") == "1"
    payload = resolve_fixture_low_source(
        fixture_key,
        league_code,
        aggregator,
        rescue=rescue,
        bundle_loader=lambda: _load_fixtures_for_http(),
    )
    if not payload:
        return jsonify(
            {
                "ok": False,
                "error": "fixture_not_found",
                "fixture_key": fixture_key,
                "league": league_code,
            }
        ), 404
    return jsonify(payload)


@app.route("/api/scrape/resilience")
@login_required(allow_public_health=True)
def api_scrape_resilience():
    """Circuit breaker + scrape ledger telemetry (no network I/O)."""
    from hibs_predictor.scrapers.robust_scrape_cycle import read_robust_scrape_status
    from hibs_predictor.scrapers.scrape_resilience import scrape_resilience_status

    return jsonify(
        {
            "ok": True,
            "resilience": scrape_resilience_status(),
            "last_cycle": read_robust_scrape_status(),
        }
    )


@app.route("/api/fve/status")
@login_required(allow_public_health=True)
def api_fve_status():
    """Cached FVE / line-trader probe — no book API calls from hibs-bet."""
    from hibs_predictor.fve_status import fetch_fve_status

    force = request.args.get("full", "0") == "1"
    return jsonify(fetch_fve_status(force=force))


@app.route("/line-trader")
@login_required(allow_public_health=True)
def line_trader_page():
    """Lightweight line-trader shell — client WS to FVE only (no server-side scrape)."""
    from hibs_predictor.fve_status import fetch_fve_status, fve_public_ws_base
    from hibs_predictor.hibs_brand import hibs_brand_context
    from hibs_predictor.product_links import infer_football_nav_active, infer_product_active, product_bar_context

    ctx = hibs_brand_context()
    ctx.update(product_bar_context(active="lines"))
    ctx.update(
        {
            "fve_status": fetch_fve_status(),
            "fve_ws_base": fve_public_ws_base(),
        }
    )
    return render_template("line_trader.html", **ctx)


_racing_inst_health_cache: Dict[str, Any] = {"t": 0.0, "payload": None}
_RACING_INST_HEALTH_TTL_SEC = float(os.getenv("HIBS_RACING_INST_HEALTH_TTL_SEC", "12"))


@app.route("/api/inst-pp/racing/health")
@login_required(allow_public_health=True)
def api_racing_inst_pp_health():
    """Inst++ racing health — HTTP probe of hibs-racing /api/health (no SQLite crossover)."""
    now = _time.monotonic()
    if (
        _racing_inst_health_cache["payload"] is not None
        and (now - float(_racing_inst_health_cache["t"])) < _RACING_INST_HEALTH_TTL_SEC
    ):
        return jsonify(_racing_inst_health_cache["payload"])
    from hibs_predictor.racing_health_aggregator import build_institutional_racing_health

    payload = build_institutional_racing_health()
    _racing_inst_health_cache["t"] = now
    _racing_inst_health_cache["payload"] = payload
    return jsonify(payload)


@app.route("/api/inst-pp/racing/stream")
@login_required(allow_public_health=True)
def api_racing_inst_pp_stream():
    """Live Inst++ racing health stream (SSE — one-way; nginx: disable buffering)."""
    import json as _json

    interval = float(os.getenv("HIBS_RACING_INST_STREAM_SEC", "15"))
    max_events = int(os.getenv("HIBS_RACING_INST_STREAM_MAX", "120"))

    def generate():
        from hibs_predictor.racing_health_aggregator import build_institutional_racing_health

        for _ in range(max(1, max_events)):
            payload = build_institutional_racing_health()
            yield f"data: {_json.dumps(payload, default=str)}\n\n"
            _time.sleep(max(3.0, interval))

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/api/health")
@login_required(allow_public_health=True)
def api_health():
    """API + scraper probes for dashboard status panel (short TTL cache)."""
    import time as _time

    from hibs_predictor.health_quality_narrative import augment_health_for_ui, health_light_requested

    light = health_light_requested()
    now = _time.monotonic()
    cache_key = "light" if light else "full"
    if (
        not light
        and _health_cache["payload"] is not None
        and (now - float(_health_cache["t"])) < _HEALTH_TTL_SEC
    ):
        return jsonify(_health_cache["payload"])
    if light:
        from hibs_predictor.health_probe import gather_health_light

        return jsonify(augment_health_for_ui(gather_health_light()))

    payload = augment_health_for_ui(gather_health())
    try:
        from hibs_predictor.api_gap_metrics import compute_league_api_gaps

        peek = Cache().peek(_all_fixtures_cache_key(include_domestic=False))
        fixtures = (peek or {}).get("all") if isinstance(peek, dict) else []
        payload["league_api_gaps"] = compute_league_api_gaps(fixtures or [])
    except Exception as exc:
        payload["league_api_gaps"] = {"error": str(exc)[:120], "rows": []}
    try:
        from hibs_predictor.rate_limiter import RateLimiter

        payload["api_sports_guard"] = RateLimiter().diagnostics("api_sports")
    except Exception:
        pass
    _health_cache["t"] = now
    _health_cache["payload"] = payload
    return jsonify(payload)


@app.route("/api/fixtures/live")
@login_required
def api_fixtures_live():
    """Lightweight in-play score poll for dashboard rows (cached live=all + optional events)."""
    from hibs_predictor.live_scores import (
        fixture_ids_likely_in_play,
        live_payload_for_dashboard_rows,
    )

    raw_ids = (request.args.get("ids") or "").strip()
    dashboard_ids = [part.strip() for part in raw_ids.split(",") if part.strip()]
    include_domestic = request.args.get("domestic") == "1"
    ck = _all_fixtures_cache_key(include_domestic=include_domestic)
    disk_bundle = Cache().peek(ck)
    if not isinstance(disk_bundle, dict):
        _schedule_dashboard_refresh()
        return jsonify({"fixtures": {}, "poll_after_sec": 45, "cache_stale": True, "cold_start": True})
    fixture_rows: List[Dict[str, Any]] = []
    if dashboard_ids:
        data = _load_fixtures_for_http(include_domestic=include_domestic)
        want = set(dashboard_ids)
        fixture_rows = [
            f for f in (data.get("all") or []) if str(f.get("id")) in want
        ]
    else:
        data = _load_fixtures_for_http(include_domestic=include_domestic)
        all_rows = data.get("all") or []
        dashboard_ids = fixture_ids_likely_in_play(all_rows)
        fixture_rows = [
            f for f in all_rows if str(f.get("id")) in set(dashboard_ids)
        ]
    include_stats = request.args.get("stats", "1") != "0"
    return jsonify(
        live_payload_for_dashboard_rows(
            aggregator,
            dashboard_ids,
            fixture_rows,
            include_events=True,
            include_stats=include_stats,
        )
    )


@app.route("/api/fixtures")
@login_required
def api_fixtures():
    league_code = request.args.get("league", "EPL")
    fixtures = fetch_next_48h_fixtures(league_code)
    return jsonify({"fixtures": fixtures, "count": len(fixtures)})


@app.route("/api/value-bets")
@login_required
def api_value_bets():
    data = _load_fixtures_for_http()
    return jsonify({"value_bets": data["value_bets"], "count": data["value_bet_count"]})


@app.route("/api/insights")
@login_required
def api_insights():
    """Handicapper-style insight digest for the current fixture window."""
    from hibs_predictor.insights import build_insights

    data = _load_fixtures_for_http()
    upcoming = _bundle_fixtures(data)
    all_rows = data.get("all") or []
    return jsonify(
        build_insights(
            upcoming,
            backfill_fixtures=[f for f in all_rows if f.get("prediction")],
        )
    )


@app.route("/api/insights/content")
@login_required
def api_insights_content():
    """HTML fragment for progressive /insights load (full build_insights, same DQ as sync page)."""
    from hibs_predictor.insights import build_insights

    include_domestic = request.args.get("domestic") == "1"
    data = _load_fixtures_for_http(
        include_domestic=include_domestic,
    )
    if data.get("cache_stale"):
        _schedule_dashboard_refresh()
    upcoming = _bundle_fixtures(data)
    all_rows = data.get("all") or []
    backfill_rows = [f for f in all_rows if f.get("prediction")]
    if backfill_rows:
        try:
            from hibs_predictor.prediction_log import backfill_snapshots_from_fixtures

            backfill_snapshots_from_fixtures(backfill_rows)
        except Exception:
            pass
    insights = build_insights(upcoming, backfill_fixtures=[])
    ctx = _insights_content_context(data, insights)
    html = render_template("_insights_deferred.html", **ctx)
    summary = insights.get("summary") or {}
    return jsonify(
        {
            "html": html,
            "summary": {
                "fixtures_eligible": summary.get("fixtures_eligible", 0),
                "fixtures_excluded": summary.get("fixtures_excluded", 0),
            },
            "value_bet_count": data.get("value_bet_count", 0),
            "cache_stale": bool(data.get("cache_stale")),
        }
    )


@app.route("/api/dashboard/recent-results")
@login_required
def api_dashboard_recent_results():
    """Recent results HTML for progressive dashboard load."""
    from hibs_predictor.recent_results import fetch_recent_results
    from hibs_predictor.tournament_focus import tournament_focus_context

    include_domestic = request.args.get("domestic") == "1"
    recent = fetch_recent_results(aggregator, include_domestic=include_domestic)
    html = render_template(
        "_dashboard_recent_results.html",
        recent_results_days_groups=recent.get("days", []),
        recent_results_days=recent.get("results_days", 3),
        display_tz_label=display_tz_label(),
        tournament_focus=tournament_focus_context(include_domestic=include_domestic),
        include_domestic=include_domestic,
    )
    return jsonify({"html": html, "total": recent.get("total", 0)})


@app.route("/api/acca/recommendations")
@login_required
def api_acca_recommendations():
    """Stat-based acca recommendations from the current enriched fixture window."""
    from hibs_predictor.acca_recommender import build_acca_recommendations
    from hibs_predictor.match_insight import build_assistant_packet

    data = _load_fixtures_for_http()
    upcoming = _bundle_fixtures(data)
    packets = [build_assistant_packet(f) for f in upcoming]
    return jsonify(build_acca_recommendations(packets))


@app.route("/tracker")
@login_required(allow_public_tracker=True)
def public_tracker_page():
    """Public read-only locked predictions + settlement ledger."""
    from hibs_predictor.auth import public_tracker_enabled
    from hibs_predictor.performance_tracker import build_public_tracker_dict

    if auth_enabled() and not public_tracker_enabled():
        abort(404)
    try:
        history_days = max(7, min(365, int(request.args.get("days", "90"))))
    except ValueError:
        history_days = 90
    tracker = build_public_tracker_dict(history_days=history_days)
    resp = make_response(
        render_template(
            "performance_tracker.html",
            tracker=tracker,
            display_tz_label=display_tz_label(),
        )
    )
    resp.headers["Cache-Control"] = "public, max-age=120"
    return resp


@app.route("/api/tracker")
@login_required(allow_public_tracker=True)
def api_public_tracker():
    from hibs_predictor.auth import public_tracker_enabled
    from hibs_predictor.performance_tracker import build_public_tracker_dict

    if auth_enabled() and not public_tracker_enabled():
        abort(404)
    try:
        history_days = max(7, min(365, int(request.args.get("days", "90"))))
    except ValueError:
        history_days = 90
    payload = build_public_tracker_dict(history_days=history_days)
    resp = jsonify(payload)
    resp.headers["Cache-Control"] = "public, max-age=120"
    return resp


@app.route("/api/tracker/export.csv")
@login_required(allow_public_tracker=True)
def api_public_tracker_csv():
    from hibs_predictor.auth import public_tracker_enabled
    from hibs_predictor.performance_tracker import export_ledger_csv

    if auth_enabled() and not public_tracker_enabled():
        abort(404)
    try:
        days = max(7, min(365, int(request.args.get("days", "365"))))
    except ValueError:
        days = 365
    body = export_ledger_csv(days=days)
    resp = make_response(body)
    resp.headers["Content-Type"] = "text/csv; charset=utf-8"
    resp.headers["Content-Disposition"] = 'attachment; filename="hibs-bet-tracker.csv"'
    resp.headers["Cache-Control"] = "public, max-age=300"
    return resp


@app.route("/performance")
@login_required
def performance_page():
    """Track record: logged model + value picks (separate from Insights handicapping)."""
    from hibs_predictor.performance_analytics import build_performance_page_dict

    try:
        history_days = max(7, min(60, int(request.args.get("days", "14"))))
    except ValueError:
        history_days = 14
    perf = build_performance_page_dict(history_days=history_days)
    return render_template(
        "performance.html",
        perf=perf,
        display_tz_label=perf.get("display_tz_label") or display_tz_label(),
    )


@app.route("/api/performance")
@login_required
def api_performance():
    from hibs_predictor.performance_analytics import build_performance_page_dict

    try:
        history_days = max(7, min(60, int(request.args.get("days", "14"))))
    except ValueError:
        history_days = 14
    return jsonify(build_performance_page_dict(history_days=history_days))


@app.route("/insights")
@login_required
def insights_page():
    """Actionable model/data/market insights built from the current fixture packets."""
    from hibs_predictor.insights import build_insights, insights_empty_shell

    progressive = _progressive_load_enabled()
    include_domestic = request.args.get("domestic") == "1"
    data = _load_fixtures_for_http(include_domestic=include_domestic)
    if data.get("cache_stale"):
        _schedule_dashboard_refresh()
    upcoming = _bundle_fixtures(data)
    if progressive:
        insights = insights_empty_shell()
        assistant_packets: List[Dict[str, Any]] = []
        assistant_recommendations = None
    else:
        all_rows = data.get("all") or []
        backfill_rows = [f for f in all_rows if f.get("prediction")]
        if backfill_rows:
            try:
                from hibs_predictor.prediction_log import backfill_snapshots_from_fixtures

                backfill_snapshots_from_fixtures(backfill_rows)
            except Exception:
                pass
        insights = build_insights(upcoming, backfill_fixtures=[])
        if _defer_assistant_on_page():
            assistant_packets = []
            assistant_recommendations = None
        else:
            assistant_bundle = _assistant_bundle(upcoming)
            assistant_packets = assistant_bundle["packets"]
            assistant_recommendations = assistant_bundle.get("recommendations")
    ctx = _insights_content_context(data, insights)
    return render_template(
        "insights.html",
        progressive_load=progressive,
        assistant_packets=assistant_packets,
        assistant_recommendations=assistant_recommendations,
        **ctx,
    )


@app.route("/tables")
@login_required
def tables_page():
    """League tables from available standings feeds, with fixture-row fallback."""
    if not isinstance(Cache().peek(_all_fixtures_cache_key(include_domestic=False)), dict):
        _schedule_dashboard_refresh()
        data = _cold_fixture_bundle(include_domestic=False)
    else:
        data = _load_fixtures_for_http(include_domestic=False)
    cold = bool(data.get("cold_start"))
    if cold:
        tables: List[Dict[str, Any]] = []
    else:
        tables = _build_league_tables(data["all"], include_live=True)
    return render_template(
        "tables.html",
        tables=tables,
        total=data["total"],
        fetch_days=_fetch_window_days(),
        display_tz_label=display_tz_label(),
        cold_start=cold,
    )


@app.route("/players")
@login_required
def players_page():
    """Player availability + form context from existing enrichment."""
    include_domestic = request.args.get("domestic") == "1"
    if not isinstance(Cache().peek(_all_fixtures_cache_key(include_domestic=include_domestic)), dict):
        _schedule_dashboard_refresh()
        data = _cold_fixture_bundle(include_domestic=include_domestic)
    else:
        data = _load_fixtures_for_http(include_domestic=include_domestic)
    return render_template(
        "players.html",
        player_row_groups=_players_groups_for_ui_data(
            data, include_domestic=include_domestic
        ),
        total=data["total"],
        fetch_days=_fetch_window_days(),
        cold_start=bool(data.get("cold_start")),
        include_domestic=include_domestic,
        tournament_focus=_tournament_focus_context(include_domestic=include_domestic),
    )


@app.route("/guide")
@login_required
def guide_page():
    """Standalone betting guide so the nav has no dead Guide item."""
    return render_template("guide.html")


@app.route("/settings")
@login_required
def settings_page():
    """Front-end preferences persisted in localStorage by the settings template."""
    return render_template(
        "settings.html",
        data_quality_ui_min=_ui_data_quality_min_pct(),
        fetch_days=_fetch_window_days(),
        allowed_fetch_days=_ALLOWED_FETCH_DAYS,
    )


@app.route("/acca")
@login_required
def acca_builder():
    data = _load_fixtures_for_http()
    return render_template("acca_builder.html", fixtures=_bundle_fixtures(data))


@app.route("/status")
@login_required
def api_status_page():
    """Dedicated API + scraper status (same probes as /api/health)."""
    return render_template("api_status.html")


_maybe_warm_fixture_cache()


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    log.info("Starting hibs-bet on http://127.0.0.1:%s", port)
    print("\n\U0001f7e2\U0001f49a hibs-bet \u2014 Starting...")
    print(f"   Open http://127.0.0.1:{port}\n")
    if _log_path:
        print(f"   Log file: {_log_path}\n")
    # threaded=True: first dashboard load can take a long time (fixtures + enrichment);
    # without threads the dev server would ignore other tabs/requests until that finishes.
    try:
        app.run(debug=False, port=port, host="127.0.0.1", threaded=True, use_reloader=False)
    except OSError as exc:
        if getattr(exc, "errno", None) in (48, 98) or "Address already in use" in str(exc):
            print(
                f"\nPort {port} is already in use. Stop the other process, or use launch/HibsBet.command "
                f"(picks a free port). Example: lsof -nP -iTCP:{port} -sTCP:LISTEN\n"
            )
        raise
