"""Fantasy Premier League public JSON API — EPL-only supplement (no API key).

Endpoints: bootstrap-static, fixtures. Used for season xG rates, table positions,
recent results, and injury availability hints when API-Football is off.
"""

from __future__ import annotations

import os
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

import requests

from hibs_predictor.cache import Cache
from hibs_predictor.team_aliases import team_names_match

_FPL_BASE = "https://fantasy.premierleague.com/api"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; HIBS/1.0; +https://hibs-bet.co.uk)",
    "Accept": "application/json",
}


def fpl_epl_enabled() -> bool:
    raw = (os.getenv("HIBS_ENABLE_FPL_EPL") or "").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    if raw in ("1", "true", "yes", "on"):
        return True
    return os.getenv("HIBS_MAX_DATA", "0").strip().lower() in ("1", "true", "yes", "on")


def fetch_bootstrap(*, cache: Optional[Cache] = None) -> Dict[str, Any]:
    cache = cache or Cache()
    key = "fpl_bootstrap_static"
    hit = cache.get(key, ttl_hours=12.0)
    if isinstance(hit, dict) and hit.get("teams"):
        return hit
    try:
        resp = requests.get(f"{_FPL_BASE}/bootstrap-static/", headers=_HEADERS, timeout=25)
        resp.raise_for_status()
        payload = resp.json()
    except Exception:
        return {}
    if not isinstance(payload, dict):
        payload = {}
    cache.set(key, payload, ttl_hours=12.0)
    return payload


def fetch_fixtures(*, cache: Optional[Cache] = None) -> List[Dict[str, Any]]:
    cache = cache or Cache()
    key = "fpl_fixtures"
    hit = cache.get(key, ttl_hours=2.0)
    if isinstance(hit, list):
        return hit
    try:
        resp = requests.get(f"{_FPL_BASE}/fixtures/", headers=_HEADERS, timeout=25)
        resp.raise_for_status()
        payload = resp.json()
    except Exception:
        cache.set(key, [], ttl_hours=0.5)
        return []
    rows = [r for r in (payload if isinstance(payload, list) else []) if isinstance(r, dict)]
    cache.set(key, rows, ttl_hours=2.0)
    return rows


def _teams_by_id(bootstrap: Dict[str, Any]) -> Dict[int, Dict[str, Any]]:
    out: Dict[int, Dict[str, Any]] = {}
    for t in bootstrap.get("teams") or []:
        if isinstance(t, dict) and t.get("id") is not None:
            out[int(t["id"])] = t
    return out


def find_team_id(team_name: str, bootstrap: Optional[Dict[str, Any]] = None) -> Optional[int]:
    bootstrap = bootstrap if bootstrap is not None else fetch_bootstrap()
    name = (team_name or "").strip()
    if not name:
        return None
    for t in bootstrap.get("teams") or []:
        if not isinstance(t, dict):
            continue
        for key in ("name", "short_name"):
            cand = str(t.get(key) or "")
            if cand and team_names_match(name, cand):
                return int(t["id"])
    return None


def _matches_played(fixtures: List[Dict[str, Any]], team_id: int) -> int:
    n = 0
    for fx in fixtures:
        if not fx.get("finished"):
            continue
        if int(fx.get("team_h") or 0) == team_id or int(fx.get("team_a") or 0) == team_id:
            n += 1
    return max(n, 1)


def team_season_xg_profile(team_name: str) -> Optional[Dict[str, Any]]:
    """
    Season xG for / against per match from FPL player aggregates.

    Returns avg_xg_for, avg_xg_against, n (matches played), team_id.
    """
    if not fpl_epl_enabled():
        return None
    bootstrap = fetch_bootstrap()
    tid = find_team_id(team_name, bootstrap)
    if tid is None:
        return None
    fixtures = fetch_fixtures()
    played = _matches_played(fixtures, tid)

    xg_for = 0.0
    gk_xgc = None
    for el in bootstrap.get("elements") or []:
        if not isinstance(el, dict) or int(el.get("team") or 0) != tid:
            continue
        try:
            xg_for += float(el.get("expected_goals") or 0)
        except (TypeError, ValueError):
            pass
        if int(el.get("element_type") or 0) == 1:
            try:
                gk_xgc = float(el.get("expected_goals_conceded") or 0)
            except (TypeError, ValueError):
                gk_xgc = None

    if xg_for <= 0.04:
        return None
    xg_against = float(gk_xgc) if gk_xgc is not None and gk_xgc > 0 else xg_for * 0.9
    return {
        "avg_xg_for": round(xg_for / played, 3),
        "avg_xg_against": round(xg_against / played, 3),
        "n": played,
        "team_id": tid,
        "team_name": team_name,
        "source": "fpl_api",
    }


def team_position_row(team_name: str) -> Optional[Dict[str, Any]]:
    """League table row from finished FPL fixtures."""
    if not fpl_epl_enabled():
        return None
    bootstrap = fetch_bootstrap()
    teams = _teams_by_id(bootstrap)
    fixtures = [fx for fx in fetch_fixtures() if fx.get("finished")]
    pts: Dict[int, int] = defaultdict(int)
    gd: Dict[int, int] = defaultdict(int)
    played: Dict[int, int] = defaultdict(int)
    for fx in fixtures:
        try:
            th, ta = int(fx["team_h"]), int(fx["team_a"])
            sh, sa = int(fx["team_h_score"]), int(fx["team_a_score"])
        except (TypeError, ValueError, KeyError):
            continue
        played[th] += 1
        played[ta] += 1
        gd[th] += sh - sa
        gd[ta] += sa - sh
        if sh > sa:
            pts[th] += 3
        elif sh < sa:
            pts[ta] += 3
        else:
            pts[th] += 1
            pts[ta] += 1
    tid = find_team_id(team_name, bootstrap)
    if tid is None:
        return None
    ranked = sorted(teams.keys(), key=lambda t: (-pts[t], -gd[t], teams[t].get("name", "")))
    try:
        rank = ranked.index(tid) + 1
    except ValueError:
        rank = 0
    return {
        "rank": rank,
        "points": pts.get(tid, 0),
        "played": played.get(tid, 0),
        "gd": gd.get(tid, 0),
        "team_id": tid,
        "team_name": teams.get(tid, {}).get("name") or team_name,
    }


def team_recent_from_fpl(team_name: str, *, limit: int = 8) -> List[Dict[str, Any]]:
    """Last finished PL matches in API-Sports-like recent shape."""
    if not fpl_epl_enabled():
        return []
    bootstrap = fetch_bootstrap()
    teams = _teams_by_id(bootstrap)
    tid = find_team_id(team_name, bootstrap)
    if tid is None:
        return []
    finished = [fx for fx in fetch_fixtures() if fx.get("finished")]
    finished.sort(key=lambda x: str(x.get("kickoff_time") or ""), reverse=True)
    out: List[Dict[str, Any]] = []
    for fx in finished:
        try:
            th, ta = int(fx["team_h"]), int(fx["team_a"])
            sh, sa = int(fx["team_h_score"]), int(fx["team_a_score"])
        except (TypeError, ValueError, KeyError):
            continue
        if tid not in (th, ta):
            continue
        home_nm = teams.get(th, {}).get("name") or "?"
        away_nm = teams.get(ta, {}).get("name") or "?"
        out.append(
            {
                "fixture": {
                    "date": fx.get("kickoff_time") or "",
                    "status": {"short": "FT"},
                },
                "teams": {
                    "home": {"id": th, "name": home_nm},
                    "away": {"id": ta, "name": away_nm},
                },
                "goals": {"home": sh, "away": sa},
                "_source": "fpl_fixtures",
            }
        )
        if len(out) >= max(1, int(limit)):
            break
    return out


def injury_hints_for_team(team_name: str) -> List[Dict[str, Any]]:
    """Players with reduced chance_of_playing_this_round (<75%)."""
    if not fpl_epl_enabled():
        return []
    bootstrap = fetch_bootstrap()
    tid = find_team_id(team_name, bootstrap)
    if tid is None:
        return []
    hints: List[Dict[str, Any]] = []
    for el in bootstrap.get("elements") or []:
        if not isinstance(el, dict) or int(el.get("team") or 0) != tid:
            continue
        try:
            chance = el.get("chance_of_playing_this_round")
            if chance is None or chance == "":
                continue
            pct = float(chance)
        except (TypeError, ValueError):
            continue
        if pct >= 75:
            continue
        hints.append(
            {
                "player": el.get("web_name"),
                "chance_pct": pct,
                "status": el.get("status"),
                "news": el.get("news"),
            }
        )
    return hints[:12]


def probe_fpl() -> Dict[str, Any]:
    try:
        boot = fetch_bootstrap(cache=Cache())
        n_teams = len(boot.get("teams") or [])
        n_el = len(boot.get("elements") or [])
        return {"ok": n_teams >= 18 and n_el >= 400, "teams": n_teams, "elements": n_el}
    except Exception as exc:
        return {"ok": False, "reason": str(exc)[:120]}
