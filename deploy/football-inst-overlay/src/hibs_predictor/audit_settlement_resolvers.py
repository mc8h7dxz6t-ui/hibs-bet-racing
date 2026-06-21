"""
Institutional++ audit settlement fallbacks when API-Football is unavailable or thin.

FT chain (per pending snapshot group):
  1. API-Football fixture id / league+date team match (caller)
  2. Football-Data.org FINISHED matches for kickoff date + competition
  3. FotMob daily matches for kickoff date (all leagues on that day)
  4. FotMob adjacent days (±1) — timezone edge cases
  5. ESPN public scoreboard — cups / internationals when FotMob lags
  6. SofaScore team events (optional; ``HIBS_SETTLE_BACKUP_SOFASCORE=1``)

Closing 1X2 chain (after FT applied):
  1. API-Football fixture odds (when client + fixture id available)
  2. The Odds API event match (best-effort; usually pre-kickoff only)
  3. Honest ``unavailable`` tag — FT still settles

Gated by ``HIBS_AUDIT_SETTLE_SCRAPE_FALLBACK`` (default on).
"""

from __future__ import annotations

import os
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv


def audit_settle_scrape_fallback_enabled() -> bool:
    load_dotenv()
    raw = (os.getenv("HIBS_AUDIT_SETTLE_SCRAPE_FALLBACK") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _kickoff_date_str(kickoff_iso: str) -> Optional[str]:
    from hibs_predictor.prediction_log import _parse_kickoff_iso

    ko = _parse_kickoff_iso(kickoff_iso)
    if ko is None:
        return None
    return ko.astimezone(timezone.utc).strftime("%Y-%m-%d")


def _match_normalized_row(
    candidates: List[Dict[str, Any]],
    *,
    home_name: str,
    away_name: str,
) -> Optional[Dict[str, Any]]:
    from hibs_predictor.prediction_log import _match_api_fixture_row

    return _match_api_fixture_row(candidates, home_name=home_name, away_name=away_name)


def _fixture_id_from_raw(raw: Dict[str, Any], *, source: str) -> Optional[int]:
    fx = raw.get("fixture") or {}
    try:
        return int(fx.get("id"))
    except (TypeError, ValueError):
        pass
    src_id = raw.get("_source_match_id")
    try:
        return int(src_id)
    except (TypeError, ValueError):
        return None


def _fdo_matches_for_row(
    row: Any,
    fdo_client: Any,
    *,
    cache: Dict[str, List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    league = str(row["league_code"] or "").strip().upper()
    day = _kickoff_date_str(str(row["kickoff_iso"] or ""))
    if not league or not day:
        return []
    try:
        from hibs_predictor.config import LEAGUES
        from hibs_predictor.season import season_candidates

        comp = (LEAGUES.get(league) or {}).get("football_data_org_id")
        if not comp:
            return []
        season = season_candidates(league_code=league)[0]
    except Exception:
        return []
    cache_key = f"fdo:{comp}:{season}:{day}"
    if cache_key not in cache:
        try:
            cache[cache_key] = (
                fdo_client.fetch_fixtures(
                    str(comp),
                    int(season),
                    status="FINISHED",
                    date_from=day,
                    date_to=day,
                )
                or []
            )
        except Exception:
            cache[cache_key] = []
    return cache[cache_key]


def _fotmob_matches_for_day(
    day: str,
    *,
    cache: Dict[str, List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    cache_key = f"fotmob:{day}"
    if cache_key in cache:
        return cache[cache_key]
    try:
        from hibs_predictor.scrapers.fotmob_client import fetch_matches_for_date

        day_dt = date.fromisoformat(day)
        payload = fetch_matches_for_date(day_dt)
    except Exception:
        cache[cache_key] = []
        return []
    rows: List[Dict[str, Any]] = []
    for league in payload.get("leagues") or []:
        if not isinstance(league, dict):
            continue
        for match in league.get("matches") or []:
            if isinstance(match, dict):
                rows.append(match)
    cache[cache_key] = rows
    return rows


def resolve_ft_from_scrape_fallback(
    row: Any,
    clients: Dict[str, Any],
    *,
    scrape_cache: Optional[Dict[str, List[Dict[str, Any]]]] = None,
) -> Tuple[Optional[int], Optional[Dict[str, Any]], str, str]:
    """
    Resolve finished match from Football-Data.org then FotMob.

    Returns (fixture_id, api_sports_like_row, note, source_tag).
  source_tag is ``football_data_org`` or ``fotmob_calendar``.
    """
    if not audit_settle_scrape_fallback_enabled():
        return None, None, "scrape_fallback_disabled", ""
    home_nm = str(row["home_name"] or "").strip()
    away_nm = str(row["away_name"] or "").strip()
    day = _kickoff_date_str(str(row["kickoff_iso"] or ""))
    if not home_nm or not away_nm or not day:
        return None, None, "no_kickoff_date", ""

    cache = scrape_cache if scrape_cache is not None else {}
    from hibs_predictor.data_aggregator import _fdo_match_to_recent_format
    from hibs_predictor.scrapers.fotmob_client import fotmob_match_to_recent_format

    fdo = clients.get("football_data_org")
    if fdo is not None:
        fdo_matches = _fdo_matches_for_row(row, fdo, cache=cache)
        normalized: List[Dict[str, Any]] = []
        for m in fdo_matches:
            norm = _fdo_match_to_recent_format(m)
            if norm is None:
                continue
            norm = dict(norm)
            norm.setdefault("fixture", {})["id"] = m.get("id")
            norm["_source_match_id"] = m.get("id")
            normalized.append(norm)
        matched = _match_normalized_row(normalized, home_name=home_nm, away_name=away_nm)
        if matched is not None:
            fid = _fixture_id_from_raw(matched, source="football_data_org")
            if fid is not None:
                return fid, matched, "resolved_fdo", "football_data_org"

    fotmob_rows = _fotmob_matches_for_day(day, cache=cache)
    fotmob_norm: List[Dict[str, Any]] = []
    for m in fotmob_rows:
        norm = fotmob_match_to_recent_format(m)
        if norm is None:
            continue
        norm = dict(norm)
        mid = m.get("id") or m.get("matchId")
        norm.setdefault("fixture", {})["id"] = mid
        norm["_source_match_id"] = mid
        fotmob_norm.append(norm)
    matched_fm = _match_normalized_row(fotmob_norm, home_name=home_nm, away_name=away_nm)
    if matched_fm is not None:
        fid = _fixture_id_from_raw(matched_fm, source="fotmob_calendar")
        if fid is not None:
            return fid, matched_fm, "resolved_fotmob", "fotmob_calendar"

    from hibs_predictor.scrapers.settlement_ft_backups import resolve_ft_from_backup_scrapers

    return resolve_ft_from_backup_scrapers(row, scrape_cache=cache)


def resolve_closing_1x2_for_settlement(
    *,
    fixture_id: Optional[int],
    raw_fixture: Dict[str, Any],
    row: Any,
    clients: Dict[str, Any],
    fetch_odds_fn: Any = None,
) -> Tuple[Dict[str, Optional[float]], str]:
    """
    Best-effort closing 1X2 for CLV join after FT settlement.

    Returns (closing_triplet, source_tag). Source may be ``api_sports``,
    ``odds_api``, or ``unavailable``.
    """
    from hibs_predictor.prediction_log import parse_closing_1x2_from_odds_response

    empty: Dict[str, Optional[float]] = {"home": None, "draw": None, "away": None}
    if fetch_odds_fn is not None and fixture_id is not None:
        try:
            odds_raw = fetch_odds_fn(int(fixture_id))
            closing = parse_closing_1x2_from_odds_response(odds_raw)
            if any(closing.get(s) for s in ("home", "draw", "away")):
                return closing, "api_sports"
        except Exception:
            pass

    if not audit_settle_scrape_fallback_enabled():
        return empty, "unavailable"

    league = str(row["league_code"] or "").strip().upper()
    home_nm = str(row["home_name"] or "").strip()
    away_nm = str(row["away_name"] or "").strip()
    if not league or not home_nm or not away_nm:
        return empty, "unavailable"

    try:
        from hibs_predictor.scrapers.odds_thin_rescue import fetch_backup_odds_for_fixture

        fixture_stub = {
            "home": home_nm,
            "away": away_nm,
            "fixture": raw_fixture.get("fixture") or {},
            "teams": raw_fixture.get("teams") or {},
        }
        backup = fetch_backup_odds_for_fixture(clients, fixture_stub, league)
        if backup:
            closing = {
                "home": backup.get("odds_home"),
                "draw": backup.get("odds_draw"),
                "away": backup.get("odds_away"),
            }
            if any(closing.get(s) for s in ("home", "draw", "away")):
                return closing, "odds_api"
    except Exception:
        pass

    return empty, "unavailable"


def build_settlement_sync_hooks(aggregator: Any) -> Dict[str, Any]:
    """
    Build kwargs for ``sync_finished_results`` from a DataAggregator.

    When API-Sports is disabled, primary fetch fns are no-ops and scrape fallbacks
    carry FT settlement.
    """

    def _noop_fetch_fixture(_fid: int) -> Dict[str, Any]:
        return {}

    hooks: Dict[str, Any] = {
        "fetch_fixture_fn": _noop_fetch_fixture,
        "fetch_odds_fn": None,
        "fetch_statistics_fn": None,
        "fetch_by_league_fn": None,
        "fetch_by_date_fn": None,
        "clients": getattr(aggregator, "clients", {}) or {},
    }
    client = hooks["clients"].get("api_sports")
    if client is not None:
        hooks["fetch_fixture_fn"] = client.fetch_fixture
        hooks["fetch_odds_fn"] = client.fetch_odds
        hooks["fetch_statistics_fn"] = getattr(client, "fetch_fixture_statistics", None)
        hooks["fetch_by_league_fn"] = client.fetch_fixtures_by_league
        hooks["fetch_by_date_fn"] = getattr(client, "fetch_fixtures_by_date", None)
    return hooks


def settlement_sync_allowed(aggregator: Any) -> Tuple[bool, str]:
    """True when pred-log-sync can run (API-Sports and/or scrape fallback)."""
    clients = getattr(aggregator, "clients", {}) or {}
    if clients.get("api_sports") is not None:
        return True, "api_sports"
    if not audit_settle_scrape_fallback_enabled():
        return False, "API_SPORTS_FOOTBALL_KEY required (scrape fallback disabled)."
    if clients.get("football_data_org") or audit_settle_scrape_fallback_enabled():
        return True, "scrape_fallback"
    return False, (
        "Need API_SPORTS_FOOTBALL_KEY or scrape sources "
        "(FOOTBALL_DATA_ORG_KEY / FotMob; set HIBS_AUDIT_SETTLE_SCRAPE_FALLBACK=1)."
    )
