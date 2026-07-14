"""
Backup FT result sources for pred-log-sync when API-Sports / FDO / FotMob primary miss.

Chain (after Football-Data.org + FotMob kickoff-day calendar):
  1. FotMob adjacent calendar days (±1) — timezone edge cases
  2. ESPN public scoreboard — no API key; strong for cups / internationals
  3. SofaScore team last events (optional; often 403 on VPS)

Gated by ``HIBS_AUDIT_SETTLE_SCRAPE_FALLBACK`` (default on).
ESPN: ``HIBS_SETTLE_BACKUP_ESPN=1`` (default on).
SofaScore: ``HIBS_SETTLE_BACKUP_SOFASCORE=0`` (default off).
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv

from hibs_predictor.scrapers.espn_client import (
    ESPN_LEAGUE_SLUG,
    espn_slug_for_league,
    event_to_recent_format as espn_event_to_recent_format,
    fetch_scoreboard as _fetch_espn_scoreboard_disk,
)


def _env_on(name: str, default: str = "1") -> bool:
    load_dotenv()
    return (os.getenv(name, default) or default).strip().lower() not in ("0", "false", "no", "off")


def settlement_backup_espn_enabled() -> bool:
    return _env_on("HIBS_SETTLE_BACKUP_ESPN", "1")


def settlement_backup_sofascore_enabled() -> bool:
    return _env_on("HIBS_SETTLE_BACKUP_SOFASCORE", "0")


def fetch_espn_scoreboard(league_slug: str, day: date, *, cache: Dict[str, Any]) -> List[Dict[str, Any]]:
    cache_key = f"espn:{league_slug}:{day.isoformat()}"
    if cache_key in cache:
        hit = cache[cache_key]
        return hit if isinstance(hit, list) else []
    rows = _fetch_espn_scoreboard_disk(league_slug, day)
    cache[cache_key] = rows
    return rows


def _kickoff_date_str(kickoff_iso: str) -> Optional[str]:
    from hibs_predictor.prediction_log import _parse_kickoff_iso

    ko = _parse_kickoff_iso(kickoff_iso)
    if ko is None:
        return None
    return ko.astimezone(timezone.utc).strftime("%Y-%m-%d")


def _match_row(
    candidates: List[Dict[str, Any]],
    *,
    home_name: str,
    away_name: str,
) -> Optional[Dict[str, Any]]:
    from hibs_predictor.prediction_log import _match_api_fixture_row

    return _match_api_fixture_row(candidates, home_name=home_name, away_name=away_name)


def _attach_source_id(raw: Dict[str, Any], *, source_id: Any) -> Dict[str, Any]:
    out = dict(raw)
    try:
        sid = int(source_id)
    except (TypeError, ValueError):
        sid = 0
    out.setdefault("fixture", {})["id"] = sid or out.get("fixture", {}).get("id")
    out["_source_match_id"] = source_id
    return out


def resolve_ft_from_fotmob_adjacent_days(
    row: Any,
    *,
    scrape_cache: Dict[str, List[Dict[str, Any]]],
) -> Tuple[Optional[int], Optional[Dict[str, Any]], str, str]:
    """FotMob calendar on kickoff day ±1 (finished matches only)."""
    from hibs_predictor.audit_settlement_resolvers import _fotmob_matches_for_day
    from hibs_predictor.scrapers.fotmob_client import fotmob_match_to_recent_format

    day = _kickoff_date_str(str(row["kickoff_iso"] or ""))
    if not day:
        return None, None, "no_kickoff_date", ""
    home_nm = str(row["home_name"] or "").strip()
    away_nm = str(row["away_name"] or "").strip()
    if not home_nm or not away_nm:
        return None, None, "no_teams", ""

    try:
        base = date.fromisoformat(day)
    except ValueError:
        return None, None, "no_kickoff_date", ""

    for offset in (-1, 1):
        alt_day = (base + timedelta(days=offset)).strftime("%Y-%m-%d")
        fotmob_rows = _fotmob_matches_for_day(alt_day, cache=scrape_cache)
        normalized: List[Dict[str, Any]] = []
        for m in fotmob_rows:
            norm = fotmob_match_to_recent_format(m)
            if norm is None:
                continue
            norm = _attach_source_id(dict(norm), source_id=m.get("id") or m.get("matchId"))
            normalized.append(norm)
        matched = _match_row(normalized, home_name=home_nm, away_name=away_nm)
        if matched is not None:
            fid = matched.get("fixture", {}).get("id")
            try:
                return int(fid), matched, "resolved_fotmob_adjacent", "fotmob_calendar_adjacent"
            except (TypeError, ValueError):
                continue
    return None, None, "unresolved_teams", ""


def resolve_ft_from_espn_scoreboard(
    row: Any,
    *,
    scrape_cache: Dict[str, Any],
) -> Tuple[Optional[int], Optional[Dict[str, Any]], str, str]:
    """ESPN public scoreboard for mapped leagues on kickoff UTC date."""
    if not settlement_backup_espn_enabled():
        return None, None, "espn_disabled", ""

    league = str(row["league_code"] or "").strip().upper()
    slug = espn_slug_for_league(league)
    day = _kickoff_date_str(str(row["kickoff_iso"] or ""))
    if not slug or not day:
        return None, None, "espn_no_slug", ""

    home_nm = str(row["home_name"] or "").strip()
    away_nm = str(row["away_name"] or "").strip()
    if not home_nm or not away_nm:
        return None, None, "no_teams", ""

    try:
        day_dt = date.fromisoformat(day)
    except ValueError:
        return None, None, "no_kickoff_date", ""

    normalized: List[Dict[str, Any]] = []
    for event in fetch_espn_scoreboard(slug, day_dt, cache=scrape_cache):
        norm = espn_event_to_recent_format(event)
        if norm is None:
            continue
        normalized.append(_attach_source_id(norm, source_id=event.get("id")))

    matched = _match_row(normalized, home_name=home_nm, away_name=away_nm)
    if matched is None:
        return None, None, "unresolved_teams", ""
    fid = matched.get("fixture", {}).get("id")
    try:
        return int(fid), matched, "resolved_espn", "espn_scoreboard"
    except (TypeError, ValueError):
        return None, None, "unresolved_id", ""


def _sofascore_event_finished(event: Dict[str, Any]) -> bool:
    status = str((event.get("status") or {}).get("type") or "").lower()
    return status in ("finished", "ended", "afterpenalties", "afterextratime")


def _sofascore_event_to_recent_format(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not _sofascore_event_finished(event):
        return None
    home_team = event.get("homeTeam") if isinstance(event.get("homeTeam"), dict) else {}
    away_team = event.get("awayTeam") if isinstance(event.get("awayTeam"), dict) else {}
    home_name = home_team.get("name") or "?"
    away_name = away_team.get("name") or "?"
    hx = event.get("homeScore") if isinstance(event.get("homeScore"), dict) else {}
    ax = event.get("awayScore") if isinstance(event.get("awayScore"), dict) else {}
    try:
        hi = int(hx.get("current") if hx.get("current") is not None else hx.get("display"))
        ai = int(ax.get("current") if ax.get("current") is not None else ax.get("display"))
    except (TypeError, ValueError):
        return None
    ts = event.get("startTimestamp")
    date_s = ""
    if ts is not None:
        try:
            date_s = datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()
        except (TypeError, ValueError, OSError):
            date_s = ""
    eid = event.get("id")
    try:
        eid_int = int(eid)
    except (TypeError, ValueError):
        eid_int = 0
    return {
        "fixture": {"id": eid_int, "date": date_s, "status": {"short": "FT"}},
        "teams": {
            "home": {"id": int(home_team.get("id") or 0), "name": home_name},
            "away": {"id": int(away_team.get("id") or 0), "name": away_name},
        },
        "goals": {"home": hi, "away": ai},
        "_source": "sofascore_events",
    }


def resolve_ft_from_sofascore_backup(
    row: Any,
    *,
    scrape_cache: Dict[str, Any],
) -> Tuple[Optional[int], Optional[Dict[str, Any]], str, str]:
    """SofaScore team last-events scan (optional; may 403 on datacenter IPs)."""
    if not settlement_backup_sofascore_enabled():
        return None, None, "sofascore_disabled", ""

    from hibs_predictor.scrapers.sofascore_client import first_team_hit, team_last_events

    home_nm = str(row["home_name"] or "").strip()
    away_nm = str(row["away_name"] or "").strip()
    kick_day = _kickoff_date_str(str(row["kickoff_iso"] or ""))
    if not home_nm or not away_nm or not kick_day:
        return None, None, "no_kickoff_date", ""

    cache_key = f"sofascore:{home_nm}:{away_nm}:{kick_day}"
    if cache_key in scrape_cache:
        events = scrape_cache[cache_key]
    else:
        events = []
        seen: set[int] = set()
        for nm in (home_nm, away_nm):
            ent = first_team_hit(nm)
            if not ent or not ent.get("id"):
                continue
            tid = int(ent["id"])
            if tid in seen:
                continue
            seen.add(tid)
            for ev in team_last_events(tid)[:20]:
                if isinstance(ev, dict):
                    events.append(ev)
        scrape_cache[cache_key] = events

    normalized: List[Dict[str, Any]] = []
    for ev in events:
        norm = _sofascore_event_to_recent_format(ev)
        if norm is None:
            continue
        ev_day = ""
        ts = ev.get("startTimestamp")
        if ts is not None:
            try:
                ev_day = datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d")
            except (TypeError, ValueError, OSError):
                ev_day = ""
        if ev_day and ev_day != kick_day:
            continue
        normalized.append(_attach_source_id(norm, source_id=ev.get("id")))

    matched = _match_row(normalized, home_name=home_nm, away_name=away_nm)
    if matched is None:
        return None, None, "unresolved_teams", ""
    fid = matched.get("fixture", {}).get("id")
    try:
        return int(fid), matched, "resolved_sofascore", "sofascore_events"
    except (TypeError, ValueError):
        return None, None, "unresolved_id", ""


def resolve_ft_from_backup_scrapers(
    row: Any,
    *,
    scrape_cache: Optional[Dict[str, Any]] = None,
) -> Tuple[Optional[int], Optional[Dict[str, Any]], str, str]:
    """
    Run supplemental FT backup chain after primary FDO + FotMob kickoff-day.

    Order: FotMob ±1 day → ESPN scoreboard → SofaScore (optional).
    """
    cache: Dict[str, Any] = scrape_cache if scrape_cache is not None else {}

    for resolver in (
        resolve_ft_from_fotmob_adjacent_days,
        resolve_ft_from_espn_scoreboard,
        resolve_ft_from_sofascore_backup,
    ):
        fid, raw, note, source = resolver(row, scrape_cache=cache)
        if fid is not None and isinstance(raw, dict):
            return fid, raw, note, source
    return None, None, "unresolved_teams", ""
