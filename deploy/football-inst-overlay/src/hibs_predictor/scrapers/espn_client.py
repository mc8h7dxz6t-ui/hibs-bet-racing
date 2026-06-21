"""ESPN public soccer scoreboard API (site.api.espn.com) — no API key.

Used for international/cup FT settlement backup and fixture-day score lookups.
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import requests

from hibs_predictor.cache import Cache

_ESPN_FINISHED = frozenset(
    {
        "STATUS_FULL_TIME",
        "STATUS_FINAL",
        "STATUS_FINAL_AET",
        "STATUS_FINAL_PEN",
        "STATUS_END_PERIOD",
    }
)

# hibs league_code → ESPN soccer scoreboard slug
ESPN_LEAGUE_SLUG: Dict[str, str] = {
    "EPL": "eng.1",
    "ELC": "eng.2",
    "EL1": "eng.3",
    "EL2": "eng.4",
    "FAC": "eng.fa",
    "SCOTTISH_PREMIERSHIP": "sco.1",
    "UCL": "uefa.champions",
    "EUROPA_LEAGUE": "uefa.europa",
    "UECL": "uefa.europa.conf",
    "LA_LIGA": "esp.1",
    "COPA_DEL_REY": "esp.copa_del_rey",
    "SERIE_A": "ita.1",
    "BUNDESLIGA": "ger.1",
    "DFB_POKAL": "ger.dfb_pokal",
    "LIGUE_1": "fra.1",
    "EREDIVISIE": "ned.1",
    "PRIMEIRA_LIGA": "por.1",
    "BELGIUM_FIRST": "bel.1",
    "DENMARK_SL": "den.1",
    "GREECE_SL": "gre.1",
    "AUSTRIA_BL": "aut.1",
    "WORLD_CUP": "fifa.world",
    "EUROS": "uefa.euro",
    "NATIONS_LEAGUE": "uefa.nations",
    "INTL_FRIENDLIES": "fifa.friendly",
}

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; HIBS/1.0; +https://hibs-bet.co.uk)",
    "Accept": "application/json",
}


def espn_slug_for_league(league_code: str) -> Optional[str]:
    return ESPN_LEAGUE_SLUG.get((league_code or "").strip().upper())


def fetch_scoreboard(
    league_slug: str,
    day: date,
    *,
    cache: Optional[Cache] = None,
) -> List[Dict[str, Any]]:
    """Finished and live events for one competition day."""
    cache = cache or Cache()
    key = f"espn_scoreboard_{league_slug}_{day.isoformat()}"
    hit = cache.get(key, ttl_hours=2.0)
    if isinstance(hit, list):
        return hit
    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{league_slug}/scoreboard"
    try:
        resp = requests.get(
            url,
            params={"dates": day.strftime("%Y%m%d")},
            headers=_HEADERS,
            timeout=20,
        )
        resp.raise_for_status()
        payload = resp.json()
    except Exception:
        cache.set(key, [], ttl_hours=0.5)
        return []
    events = payload.get("events") if isinstance(payload, dict) else None
    rows = [e for e in (events or []) if isinstance(e, dict)]
    cache.set(key, rows, ttl_hours=2.0)
    return rows


def _parse_event_date(event: Dict[str, Any]) -> Optional[datetime]:
    raw = event.get("date")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None


def event_finished(event: Dict[str, Any]) -> bool:
    status = event.get("status") if isinstance(event.get("status"), dict) else {}
    stype = status.get("type") if isinstance(status.get("type"), dict) else {}
    name = str(stype.get("name") or "").upper()
    if name in _ESPN_FINISHED:
        return True
    return stype.get("completed") is True and stype.get("state") == "post"


def _competitors(event: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    comps = event.get("competitions") or []
    if not comps or not isinstance(comps[0], dict):
        return None, None
    home = away = None
    for c in comps[0].get("competitors") or []:
        if not isinstance(c, dict):
            continue
        if c.get("homeAway") == "home":
            home = c
        elif c.get("homeAway") == "away":
            away = c
    return home, away


def _status_short(event: Dict[str, Any]) -> str:
    status = event.get("status") if isinstance(event.get("status"), dict) else {}
    stype = status.get("type") if isinstance(status.get("type"), dict) else {}
    name = str(stype.get("name") or "").upper()
    state = str(stype.get("state") or "").lower()
    if event_finished(event):
        return "FT"
    if state == "in" or "IN_PROGRESS" in name:
        return "LIVE"
    if state == "pre" or "SCHEDULED" in name:
        return "NS"
    short = status.get("shortDetail") or stype.get("shortDetail")
    if short:
        return str(short)[:12]
    return "NS"


def event_to_fixture_format(event: Dict[str, Any], league_code: str) -> Optional[Dict[str, Any]]:
    """Normalize ESPN scoreboard event → app fixture shape (scheduled, live, or FT)."""
    home_c, away_c = _competitors(event)
    if not home_c or not away_c:
        return None
    home_team = home_c.get("team") if isinstance(home_c.get("team"), dict) else {}
    away_team = away_c.get("team") if isinstance(away_c.get("team"), dict) else {}
    home_name = home_team.get("displayName") or home_team.get("shortDisplayName") or ""
    away_name = away_team.get("displayName") or away_team.get("shortDisplayName") or ""
    if not home_name or not away_name:
        return None
    ko = _parse_event_date(event)
    if not ko:
        return None
    date_s = ko.isoformat()
    try:
        eid_int = int(event.get("id"))
    except (TypeError, ValueError):
        eid_int = 0
    goals: Dict[str, Any] = {}
    for side, comp in (("home", home_c), ("away", away_c)):
        try:
            goals[side] = int(comp.get("score"))
        except (TypeError, ValueError):
            pass
    short = _status_short(event)
    return {
        "fixture": {
            "id": f"espn_{eid_int}" if eid_int else None,
            "date": date_s,
            "status": {"short": short},
        },
        "teams": {
            "home": {"id": int(home_team.get("id") or 0), "name": home_name},
            "away": {"id": int(away_team.get("id") or 0), "name": away_name},
        },
        "home": {"id": int(home_team.get("id") or 0), "name": home_name},
        "away": {"id": int(away_team.get("id") or 0), "name": away_name},
        "goals": goals if goals else None,
        "date": date_s,
        "league": league_code,
        "source": "espn_scoreboard",
    }


def espn_fixtures_enabled() -> bool:
    """Targeted fixture fallback when API-Sports off and FDO/FotMob thin."""
    raw = (os.getenv("HIBS_ENABLE_ESPN_FIXTURES") or "").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    if raw in ("1", "true", "yes", "on"):
        return True
    try:
        from hibs_predictor.scrape_first import scrape_first_mode

        if scrape_first_mode():
            return True
    except Exception:
        pass
    settle = (os.getenv("HIBS_SETTLE_BACKUP_ESPN") or "1").strip().lower()
    return settle not in ("0", "false", "no", "off")


def fixtures_for_league(
    league_code: str,
    day_start: date,
    day_end: date,
    *,
    cache: Optional[Cache] = None,
) -> List[Dict[str, Any]]:
    """Upcoming/live/FT fixtures from ESPN public scoreboard (no API key)."""
    slug = espn_slug_for_league(league_code)
    if not slug:
        return []
    cache = cache or Cache()
    out: List[Dict[str, Any]] = []
    day = day_start
    while day <= day_end:
        for event in fetch_scoreboard(slug, day, cache=cache):
            norm = event_to_fixture_format(event, league_code)
            if norm:
                out.append(norm)
        day += timedelta(days=1)
    return out


def event_to_recent_format(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Normalize finished ESPN event → API-Sports-like row."""
    if not event_finished(event):
        return None
    home_c, away_c = _competitors(event)
    if not home_c or not away_c:
        return None
    home_team = home_c.get("team") if isinstance(home_c.get("team"), dict) else {}
    away_team = away_c.get("team") if isinstance(away_c.get("team"), dict) else {}
    home_name = home_team.get("displayName") or home_team.get("shortDisplayName") or "?"
    away_name = away_team.get("displayName") or away_team.get("shortDisplayName") or "?"
    try:
        hi = int(home_c.get("score"))
        ai = int(away_c.get("score"))
    except (TypeError, ValueError):
        return None
    ko = _parse_event_date(event)
    date_s = ko.isoformat() if ko else ""
    try:
        eid_int = int(event.get("id"))
    except (TypeError, ValueError):
        eid_int = 0
    return {
        "fixture": {"id": eid_int, "date": date_s, "status": {"short": "FT"}},
        "teams": {
            "home": {"id": int(home_team.get("id") or 0), "name": home_name},
            "away": {"id": int(away_team.get("id") or 0), "name": away_name},
        },
        "goals": {"home": hi, "away": ai},
        "_source": "espn_scoreboard",
    }


def probe_scoreboard(league_code: str = "EPL") -> Dict[str, Any]:
    """Health probe: fetch today's scoreboard for a mapped league."""
    slug = espn_slug_for_league(league_code)
    if not slug:
        return {"ok": False, "reason": "no_slug", "league_code": league_code}
    try:
        rows = fetch_scoreboard(slug, date.today(), cache=Cache())
        return {"ok": len(rows) >= 0, "league_slug": slug, "event_count": len(rows)}
    except Exception as exc:
        return {"ok": False, "reason": str(exc)[:120]}
