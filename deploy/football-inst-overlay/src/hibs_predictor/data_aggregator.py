"""Data aggregator that enriches fixtures with multi-API data."""

import os
import re
import threading
import time
import unicodedata
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv

from hibs_predictor.api_clients import (
    ApiSportsFootballClient,
    FootballDataOrgClient,
    SportsMonkClient,
    OddsApiClient,
    StatsApiClient,
)
from hibs_predictor.betting_engine import TeamStrengthCalculator
from hibs_predictor.config import LEAGUES
from hibs_predictor.cache import Cache
from hibs_predictor.data_quality import _has_stats, compute_fixture_data_quality
from hibs_predictor.scrapers.supplemental import collect_supplemental
from hibs_predictor.fixture_utils import (
    coerce_team_id,
    fixture_team_id,
    fixture_team_name,
    is_cup_competition,
    normalize_position_dict,
)
from hibs_predictor.scrapers import soccerstats_standings as soccerstats_standings
from hibs_predictor.scrapers.fotmob_client import FOTMOB_XG_LEAGUE_FALLBACK


def _project_root() -> str:
    """Repository root (parent of `src/`), regardless of process cwd."""
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _load_dotenv_from_project() -> None:
    """Load `.env` from the repo root so fixture APIs work when cwd is not the project folder."""
    root = _project_root()
    load_dotenv(os.path.join(root, ".env"))
    load_dotenv(os.path.join(root, ".env.local"))


def _looks_like_placeholder(value: str) -> bool:
    low = value.strip().lower()
    if not low:
        return True
    if "your_" in low and "here" in low:
        return True
    if low in ("xxx", "test", "none", "changeme", "null", "n/a", "na"):
        return True
    return False


def _env_first_usable(*names: str) -> str:
    for name in names:
        raw = os.getenv(name)
        if raw is None:
            continue
        val = raw.strip().strip('"').strip("'").lstrip("\ufeff")
        if not val or val.startswith("#"):
            continue
        if _looks_like_placeholder(val):
            continue
        return val
    return ""


def _env_flag_truthy(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in ("1", "true", "yes", "on")


def _season_candidates(now: Optional[datetime] = None, league_code: Optional[str] = None) -> List[int]:
    """Current domestic season id plus previous season for completed/thin windows."""
    from hibs_predictor.season import season_candidates

    return season_candidates(now, league_code=league_code)


def _cup_domestic_stats_league(league_code: str) -> Tuple[str, Optional[int]]:
    """When cup competition stats are empty, use parent domestic league (e.g. Coupe → Ligue 1)."""
    code = (league_code or "").strip().upper()
    parent = FOTMOB_XG_LEAGUE_FALLBACK.get(code)
    if not parent:
        return code, LEAGUES.get(code, {}).get("api_sports_id")
    return parent, LEAGUES.get(parent, {}).get("api_sports_id")


def _norm_team_name(name: Any) -> str:
    text = unicodedata.normalize("NFKD", str(name or ""))
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    text = re.sub(r"[^a-z0-9]+", " ", text).strip()
    for suffix in (" fc", " afc", " cf", " sc"):
        if text.endswith(suffix):
            text = text[: -len(suffix)].strip()
    return text


def _football_data_position_from_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "position": entry.get("position"),
        "played": entry.get("playedGames", 0),
        "won": entry.get("won", 0),
        "drawn": entry.get("draw", 0),
        "lost": entry.get("lost", 0),
        "goals_for": entry.get("goalsFor", 0),
        "goals_against": entry.get("goalsAgainst", 0),
        "goal_diff": entry.get("goalDifference", 0),
        "points": entry.get("points", 0),
        "form": entry.get("form", ""),
        "source": "football_data_org",
    }


def _effective_skip_odds_api(clients: Dict[str, Any]) -> bool:
    """Use The Odds API when configured unless sharp ingress or HIBS_SKIP_ODDS_API opts out."""
    if "odds_api" not in clients:
        return True
    try:
        from hibs_predictor.ingress.oddspapi_client import oddspapi_enabled

        if oddspapi_enabled() and "oddspapi" in clients:
            return True
    except Exception:
        pass
    return _env_flag_truthy("HIBS_SKIP_ODDS_API")


def _enrich_fresh_minutes() -> float:
    try:
        return max(1.0, float(os.getenv("HIBS_ENRICH_FRESH_MINUTES", "15")))
    except ValueError:
        return 15.0


def _enriched_disk_ttl_hours(
    fixture: Dict[str, Any],
    enriched: Dict[str, Any],
    home_id: Optional[int],
    away_id: Optional[int],
) -> float:
    """Longer disk cache for future kickoffs; short TTL when core blocks are still thin."""
    if DataAggregator._enriched_needs_recent_refetch(enriched, home_id, away_id):
        return 0.25
    try:
        from hibs_predictor.deep_enrich import deep_enrich_today_only, fixture_is_today

        if deep_enrich_today_only() and not fixture_is_today(fixture):
            return max(2.0, float(os.getenv("HIBS_ENRICH_CACHE_HOURS_FUTURE", "8")))
    except Exception:
        pass
    return 2.0


def _enrich_api_semaphore_size() -> int:
    """Cap concurrent API team/history calls during bundle builds (reduces 429 bursts)."""
    raw = os.getenv("HIBS_ENRICH_API_SEM", "").strip()
    if raw:
        try:
            return max(1, min(16, int(raw)))
        except ValueError:
            pass
    if _env_flag_truthy("HIBS_MAX_DATA"):
        return 2
    return 4


def _team_recent_mem_ttl_sec() -> float:
    try:
        return max(60.0, float(os.getenv("HIBS_TEAM_RECENT_MEM_TTL_SEC", "300")))
    except ValueError:
        return 300.0


def _effective_skip_rapid_stats_xg(clients: Dict[str, Any]) -> bool:
    """Default skips RapidAPI stats xG; HIBS_MAX_DATA=1 + stats_api client enables it without editing HIBS_SKIP_RAPID_STATS_XG."""
    raw = os.getenv("HIBS_SKIP_RAPID_STATS_XG", "1").strip().lower()
    if raw not in ("1", "true", "yes"):
        return False
    if _env_flag_truthy("HIBS_MAX_DATA") and "stats_api" in clients:
        return False
    return True


def _float_from_stat_block(block: Any) -> Optional[float]:
    if block is None:
        return None
    if isinstance(block, dict):
        for key in ("total", "average", "value"):
            v = block.get(key)
            if v is None:
                continue
            try:
                return float(v)
            except (TypeError, ValueError):
                continue
        return None
    try:
        return float(block)
    except (TypeError, ValueError):
        return None


def _extract_xg_totals_from_api_stats(team_stats: Dict[str, Any]) -> Tuple[Optional[float], Optional[float]]:
    """
    Season xG totals from API-Football teams/statistics when present (goals.for.expected etc.).
    Returns (xg_for_total, xg_against_total) or (None, None).
    """
    goals = team_stats.get("goals") if isinstance(team_stats.get("goals"), dict) else {}
    xg_for = _float_from_stat_block((goals.get("for") or {}).get("expected"))
    xg_against = _float_from_stat_block((goals.get("against") or {}).get("expected"))
    if xg_for is None:
        xg_for = _float_from_stat_block(team_stats.get("expected_goals"))
    if xg_against is None:
        xg_against = _float_from_stat_block(team_stats.get("expected_goals_against"))
    if xg_for is not None and xg_for > 0.04:
        return xg_for, xg_against if (xg_against is not None and xg_against > 0) else xg_for
    return None, None


def _extract_goals_totals_from_api_stats(team_stats: Dict[str, Any]) -> Tuple[int, int]:
    """Normalize API-Football teams/statistics goals shape to (goals_for, goals_against)."""
    goals = team_stats.get("goals") or {}
    out_for, out_against = 0, 0
    for side_key, target in (("for", "for"), ("against", "against")):
        side = goals.get(side_key) or {}
        total = side.get("total")
        if isinstance(total, dict):
            v = total.get("total")
            if v is None:
                v = (total.get("home") or 0) + (total.get("away") or 0)
            try:
                val = int(v or 0)
            except (TypeError, ValueError):
                val = 0
        else:
            try:
                val = int(total or 0)
            except (TypeError, ValueError):
                val = 0
        if side_key == "for":
            out_for = val
        else:
            out_against = val
    return out_for, out_against


def _match_goals_for_team(
    match: Dict[str, Any],
    team_id: Optional[int],
    *,
    team_name: str = "",
) -> Optional[tuple[int, int]]:
    """Return (gf, ga) for the focal team in a finished match row."""
    from hibs_predictor.live_scores import _team_names_match

    teams = match.get("teams", {}) or {}
    goals = match.get("goals", {}) or {}
    home_g = goals.get("home")
    away_g = goals.get("away")
    if home_g is None or away_g is None:
        return None
    try:
        hg = int(home_g)
        ag = int(away_g)
    except (TypeError, ValueError):
        return None
    hid = coerce_team_id((teams.get("home") or {}).get("id"))
    aid = coerce_team_id((teams.get("away") or {}).get("id"))
    tid = coerce_team_id(team_id)
    if tid is not None:
        if hid == tid:
            return hg, ag
        if aid == tid:
            return ag, hg
    hn = str((teams.get("home") or {}).get("name") or "")
    an = str((teams.get("away") or {}).get("name") or "")
    if team_name and _team_names_match(team_name, hn):
        return hg, ag
    if team_name and _team_names_match(team_name, an):
        return ag, hg
    return None


def _recent_match_rates(
    matches: List[Dict[str, Any]],
    team_id: int,
    *,
    team_name: str = "",
) -> Dict[str, float]:
    """BTTS / over rates and per-game goals from the team's last finished matches."""
    if not matches:
        return {
            "btts_rate": 0.0,
            "over15_rate": 0.0,
            "over25_rate": 0.0,
            "avg_gf": 0.0,
            "avg_ga": 0.0,
            "n": 0.0,
        }
    btts = o15 = o25 = 0
    tgf = tga = 0.0
    n = 0
    for match in matches[:10]:
        scored = _match_goals_for_team(match, team_id, team_name=team_name)
        if not scored:
            continue
        gf, ga = scored
        n += 1
        tgf += gf
        tga += ga
        if gf > 0 and ga > 0:
            btts += 1
        if gf + ga > 1:
            o15 += 1
        if gf + ga > 2:
            o25 += 1
    if n == 0:
        return {
            "btts_rate": 0.0,
            "over15_rate": 0.0,
            "over25_rate": 0.0,
            "avg_gf": 0.0,
            "avg_ga": 0.0,
            "n": 0.0,
        }
    return {
        "btts_rate": btts / n,
        "over15_rate": o15 / n,
        "over25_rate": o25 / n,
        "avg_gf": tgf / n,
        "avg_ga": tga / n,
        "n": float(n),
    }


def _implied_prob(odds: float) -> float:
    if odds is None or odds <= 1.0:
        return 0.0
    return 1.0 / float(odds)


def _fdo_match_to_recent_format(match: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Normalize Football-Data.org finished match → API-Sports-like shape for rate calculators."""
    ht = match.get("homeTeam") or {}
    at = match.get("awayTeam") or {}
    if not isinstance(ht, dict) or not isinstance(at, dict):
        return None
    hid, aid = ht.get("id"), at.get("id")
    ft = (match.get("score") or {}).get("fullTime") or {}
    home_g, away_g = ft.get("home"), ft.get("away")
    if home_g is None or away_g is None:
        return None
    try:
        return {
            "fixture": {
                "date": match.get("utcDate") or match.get("date") or "",
                "status": {"short": "FT"},
            },
            "teams": {
                "home": {"id": int(hid), "name": ht.get("name") or ht.get("shortName") or "?"},
                "away": {"id": int(aid), "name": at.get("name") or at.get("shortName") or "?"},
            },
            "goals": {"home": int(home_g), "away": int(away_g)},
            "_source": "football_data_org",
        }
    except (TypeError, ValueError):
        return None


def _stats_from_fdo_matches(matches: List[Dict[str, Any]]) -> Dict[str, Any]:
    from hibs_predictor.api_clients import FootballDataOrgClient

    if not matches:
        return {}
    parsed = FootballDataOrgClient.parse_form_from_matches(matches)
    n = min(10, len(matches))
    if n == 0:
        return {}
    gf = float(parsed.get("goals_for") or 0)
    ga = float(parsed.get("goals_against") or 0)
    return {
        "goals_for": gf,
        "goals_against": ga,
        "played": n,
        "wins": parsed.get("wins", 0),
        "draws": parsed.get("draws", 0),
        "losses": parsed.get("losses", 0),
        "source": "football_data_org",
    }


def _empty_rates() -> Dict[str, float]:
    return {
        "btts_rate": 0.0,
        "over15_rate": 0.0,
        "over25_rate": 0.0,
        "avg_gf": 0.0,
        "avg_ga": 0.0,
        "n": 0.0,
    }


def _odds_bookmaker_display_name(bm: Dict[str, Any]) -> str:
    """Prefer human title from The Odds API (e.g. 'Bet Victor') over internal keys."""
    return str(bm.get("title") or bm.get("name") or bm.get("key") or "").strip()


def _odds_teams_match(fixture_home: str, fixture_away: str, event_home: str, event_away: str) -> bool:
    from hibs_predictor.live_scores import _team_names_match

    fh, fa = (fixture_home or "").strip(), (fixture_away or "").strip()
    eh, ea = (event_home or "").strip(), (event_away or "").strip()
    if not fh or not fa or not eh or not ea:
        return False
    if _team_names_match(fh, eh) and _team_names_match(fa, ea):
        return True
    return _team_names_match(fh, ea) and _team_names_match(fa, eh)


def _odds_teams_swapped(fixture_home: str, fixture_away: str, event_home: str, event_away: str) -> bool:
    from hibs_predictor.live_scores import _team_names_match

    return _team_names_match(fixture_home or "", event_away or "") and _team_names_match(
        fixture_away or "", event_home or ""
    )


def _odds_kickoff_matches(
    fixture: Dict[str, Any],
    event: Dict[str, Any],
    *,
    tolerance_hours: float = 6.0,
) -> bool:
    from hibs_predictor.display_tz import parse_kickoff_utc

    fx_raw = fixture.get("date")
    if fx_raw is None and isinstance(fixture.get("fixture"), dict):
        fx_raw = fixture["fixture"].get("date")
    fx_dt = parse_kickoff_utc(fx_raw)
    ev_dt = parse_kickoff_utc(event.get("commence_time"))
    if fx_dt is None or ev_dt is None:
        return True
    return abs((fx_dt - ev_dt).total_seconds()) <= tolerance_hours * 3600.0


def _odds_event_matches_fixture(
    event: Dict[str, Any],
    fixture: Dict[str, Any],
    home_name: str,
    away_name: str,
) -> bool:
    eh = str(event.get("home_team") or "")
    ea = str(event.get("away_team") or "")
    if not _odds_teams_match(home_name, away_name, eh, ea):
        return False
    return _odds_kickoff_matches(fixture, event)


def _odds_outcome_side(
    outcome_name: str,
    home_name: str,
    away_name: str,
    *,
    teams_swapped: bool,
) -> Optional[str]:
    from hibs_predictor.live_scores import _team_names_match

    oname = (outcome_name or "").strip()
    if "draw" in oname.lower():
        return "draw"
    if teams_swapped:
        if _team_names_match(away_name, oname):
            return "home"
        if _team_names_match(home_name, oname):
            return "away"
    else:
        if _team_names_match(home_name, oname):
            return "home"
        if _team_names_match(away_name, oname):
            return "away"
    return None


def _empty_odds_bundle() -> Dict[str, Any]:
    return {
        "odds_home": None,
        "odds_draw": None,
        "odds_away": None,
        "odds_available": False,
        "all_bookmaker_odds": [],
        "odds_secondary": {"home": None, "draw": None, "away": None},
        "odds_cross_max_implied_diff_pct": 0.0,
        "odds_cross_book_max_implied_diff_pct": 0.0,
        "odds_primary_source": "partial",
        "market_odds": {},
        "best_odds_1x2": {"home": None, "draw": None, "away": None},
        "best_odds_source": {"home": None, "draw": None, "away": None},
        "sharp_anchor_implied": {},
    }


def _max_implied_delta_pct(
    a: Optional[float],
    b: Optional[float],
    c: Optional[float],
    x: Optional[float],
    y: Optional[float],
    z: Optional[float],
) -> float:
    if not all(v and v > 1.0 for v in (a, b, c, x, y, z)):
        return 0.0
    d = 0.0
    for p, q in ((a, x), (b, y), (c, z)):
        d = max(d, abs(_implied_prob(p) - _implied_prob(q)) * 100.0)
    return round(d, 2)


def _normalize_bookmaker_odds_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Dedupe by bookmaker label; keep best price per outcome; ensure display names."""
    merged: Dict[str, Dict[str, Any]] = {}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        name = str(row.get("bookmaker") or row.get("name") or "").strip()
        if not name:
            src = str(row.get("source") or "book")
            name = src.replace("_", " ").title()
        key = name.lower()
        cur = merged.get(key)
        if cur is None:
            cur = {"bookmaker": name, "source": row.get("source")}
            merged[key] = cur
        for side in (
            "home",
            "draw",
            "away",
            "over_1_5",
            "under_1_5",
            "over_2_5",
            "under_2_5",
            "over_3_5",
            "under_3_5",
            "btts_yes",
            "btts_no",
        ):
            raw = row.get(side)
            try:
                price = float(raw) if raw is not None else 0.0
            except (TypeError, ValueError):
                continue
            if price <= 1.0:
                continue
            prev = cur.get(side)
            if prev is None or price > float(prev):
                cur[side] = price
    keep_sides = (
        "home",
        "draw",
        "away",
        "over_1_5",
        "under_1_5",
        "over_2_5",
        "under_2_5",
        "over_3_5",
        "under_3_5",
        "btts_yes",
        "btts_no",
    )
    out = [r for r in merged.values() if any(r.get(s) for s in keep_sides)]
    out.sort(key=lambda r: str(r.get("bookmaker") or ""))
    return out


def compute_best_line_from_bookmakers(
    all_bookmakers: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Best decimal price per 1X2 outcome across bookmaker rows, plus cross-book disagreement.

    Returns keys: best_odds_1x2, best_odds_source, odds_cross_book_max_implied_diff_pct,
    sharp_anchor_implied (median de-vig 1X2 or Pinnacle when listed).
    """
    sides = ("home", "draw", "away")
    best: Dict[str, Optional[float]] = {s: None for s in sides}
    source: Dict[str, Optional[str]] = {s: None for s in sides}
    by_side_prices: Dict[str, List[float]] = {s: [] for s in sides}
    pinnacle: Dict[str, Optional[float]] = {s: None for s in sides}

    for row in all_bookmakers or []:
        if not isinstance(row, dict):
            continue
        bm_name = str(row.get("bookmaker") or row.get("name") or "").strip()
        is_pinnacle = "pinnacle" in bm_name.lower()
        for side in sides:
            raw = row.get(side)
            try:
                price = float(raw) if raw is not None else 0.0
            except (TypeError, ValueError):
                continue
            if price <= 1.0:
                continue
            by_side_prices[side].append(price)
            if is_pinnacle:
                cur = pinnacle.get(side)
                pinnacle[side] = price if cur is None else max(cur, price)
            cur_best = best[side]
            if cur_best is None or price > cur_best:
                best[side] = price
                source[side] = bm_name or row.get("source") or "unknown"

    cross = 0.0
    for side in sides:
        prices = by_side_prices[side]
        if len(prices) < 2:
            continue
        impls = [_implied_prob(p) for p in prices if p > 1.0]
        if len(impls) >= 2:
            cross = max(cross, (max(impls) - min(impls)) * 100.0)

    sharp: Dict[str, float] = {}
    from hibs_predictor.odds_devig import odds_ratio_devig_probs, shin_devig_probs

    if all(pinnacle.get(s) and pinnacle[s] > 1.0 for s in sides):
        pin_odds = {s: float(pinnacle[s]) for s in sides}  # type: ignore[arg-type]
        sharp = odds_ratio_devig_probs(pin_odds)
        sharp_shin = shin_devig_probs(pin_odds)
    else:
        med_odds: Dict[str, float] = {}
        for side in sides:
            prices = sorted(by_side_prices[side])
            if not prices:
                continue
            mid = prices[len(prices) // 2]
            med_odds[side] = mid
        sharp = {}
        sharp_shin = {}
        if len(med_odds) == 3:
            sharp = odds_ratio_devig_probs(med_odds)
            sharp_shin = shin_devig_probs(med_odds)

    return {
        "best_odds_1x2": best,
        "best_odds_source": source,
        "odds_cross_book_max_implied_diff_pct": round(cross, 2),
        "sharp_anchor_implied": sharp,
        "sharp_anchor_implied_shin": sharp_shin,
    }


def _parse_api_sports_side_markets(odds_data: List[Dict[str, Any]]) -> Dict[str, Any]:
    """BTTS and Over/Under lines from API-Football odds (best decimal per selection)."""
    btts_yes: List[float] = []
    btts_no: List[float] = []
    over15: List[float] = []
    under15: List[float] = []
    over25: List[float] = []
    under25: List[float] = []
    over35: List[float] = []
    under35: List[float] = []
    for entry in odds_data or []:
        for bm in entry.get("bookmakers", []) or []:
            for bet in bm.get("bets", []) or []:
                name = (bet.get("name") or "").strip()
                vals = bet.get("values", []) or []
                if name == "Both Teams To Score":
                    for v in vals:
                        val = (v.get("value") or "").strip().lower()
                        try:
                            p = float(v.get("odd", 0) or 0)
                        except (TypeError, ValueError):
                            continue
                        if p <= 1.0:
                            continue
                        if val == "yes":
                            btts_yes.append(p)
                        elif val == "no":
                            btts_no.append(p)
                elif name in ("Goals Over/Under", "Over/Under", "Total Goals"):
                    for v in vals:
                        val = (v.get("value") or "").strip().lower()
                        try:
                            p = float(v.get("odd", 0) or 0)
                        except (TypeError, ValueError):
                            continue
                        if p <= 1.0:
                            continue
                        if "over 1.5" in val or val in ("o1.5", "over 1.5"):
                            over15.append(p)
                        elif "under 1.5" in val or val in ("u1.5", "under 1.5"):
                            under15.append(p)
                        if "over 2.5" in val or val in ("o2.5", "over 2.5"):
                            over25.append(p)
                        elif "under 2.5" in val or val in ("u2.5", "under 2.5"):
                            under25.append(p)
                        if "over 3.5" in val or val in ("o3.5", "over 3.5"):
                            over35.append(p)
                        elif "under 3.5" in val or val in ("u3.5", "under 3.5"):
                            under35.append(p)
    out: Dict[str, Any] = {}
    if btts_yes:
        out["btts_yes"] = max(btts_yes)
    if btts_no:
        out["btts_no"] = max(btts_no)
    if over15:
        out["over_1_5"] = max(over15)
    if under15:
        out["under_1_5"] = max(under15)
    if over25:
        out["over_2_5"] = max(over25)
    if under25:
        out["under_2_5"] = max(under25)
    if over35:
        out["over_3_5"] = max(over35)
    if under35:
        out["under_3_5"] = max(under35)
    return out


def _odds_api_decimal_price(raw: Any) -> Optional[float]:
    try:
        price = float(raw or 0)
    except (TypeError, ValueError):
        return None
    return price if price > 1.0 else None


def _odds_api_totals_point(raw: Any) -> Optional[float]:
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _odds_api_apply_markets_to_book_row(
    bm: Dict[str, Any],
    bm_odds: Dict[str, Any],
    *,
    home_display: str,
    away_display: str,
    teams_swapped: bool,
    side_acc: Dict[str, List[float]],
) -> None:
    """Fill 1X2 and side-market prices on a bookmaker row from The Odds API markets."""
    for market in bm.get("markets", []) or []:
        if not isinstance(market, dict):
            continue
        mkey = market.get("key")
        if mkey == "h2h":
            for o in market.get("outcomes", []) or []:
                price = _odds_api_decimal_price(o.get("price"))
                if price is None:
                    continue
                side = _odds_outcome_side(
                    str(o.get("name") or ""),
                    home_display,
                    away_display,
                    teams_swapped=teams_swapped,
                )
                if side == "draw":
                    bm_odds["draw"] = max(bm_odds.get("draw") or 0.0, price)
                elif side == "home":
                    bm_odds["home"] = max(bm_odds.get("home") or 0.0, price)
                elif side == "away":
                    bm_odds["away"] = max(bm_odds.get("away") or 0.0, price)
        elif mkey == "totals":
            for o in market.get("outcomes", []) or []:
                price = _odds_api_decimal_price(o.get("price"))
                if price is None:
                    continue
                point = _odds_api_totals_point(o.get("point"))
                name = str(o.get("name") or "").lower()
                if point == 1.5:
                    if "over" in name:
                        bm_odds["over_1_5"] = max(bm_odds.get("over_1_5") or 0.0, price)
                        side_acc["over_1_5"].append(price)
                    elif "under" in name:
                        bm_odds["under_1_5"] = max(bm_odds.get("under_1_5") or 0.0, price)
                        side_acc["under_1_5"].append(price)
                elif point == 2.5:
                    if "over" in name:
                        bm_odds["over_2_5"] = max(bm_odds.get("over_2_5") or 0.0, price)
                        side_acc["over_2_5"].append(price)
                    elif "under" in name:
                        bm_odds["under_2_5"] = max(bm_odds.get("under_2_5") or 0.0, price)
                        side_acc["under_2_5"].append(price)
                elif point == 3.5:
                    if "over" in name:
                        bm_odds["over_3_5"] = max(bm_odds.get("over_3_5") or 0.0, price)
                        side_acc["over_3_5"].append(price)
                    elif "under" in name:
                        bm_odds["under_3_5"] = max(bm_odds.get("under_3_5") or 0.0, price)
                        side_acc["under_3_5"].append(price)
        elif mkey == "btts":
            for o in market.get("outcomes", []) or []:
                price = _odds_api_decimal_price(o.get("price"))
                if price is None:
                    continue
                name = str(o.get("name") or "").strip().lower()
                if name == "yes":
                    bm_odds["btts_yes"] = max(bm_odds.get("btts_yes") or 0.0, price)
                    side_acc["btts_yes"].append(price)
                elif name == "no":
                    bm_odds["btts_no"] = max(bm_odds.get("btts_no") or 0.0, price)
                    side_acc["btts_no"].append(price)


def _parse_odds_api_event_side_markets(event: Dict[str, Any]) -> Dict[str, Any]:
    """Best decimal BTTS / totals lines across bookmakers for one Odds API event."""
    side_acc: Dict[str, List[float]] = {
        "btts_yes": [],
        "btts_no": [],
        "over_1_5": [],
        "under_1_5": [],
        "over_2_5": [],
        "under_2_5": [],
        "over_3_5": [],
        "under_3_5": [],
    }
    for bm in event.get("bookmakers", []) or []:
        if not isinstance(bm, dict):
            continue
        scratch: Dict[str, Any] = {}
        _odds_api_apply_markets_to_book_row(
            bm,
            scratch,
            home_display="",
            away_display="",
            teams_swapped=False,
            side_acc=side_acc,
        )
    out: Dict[str, Any] = {}
    if side_acc["btts_yes"]:
        out["btts_yes"] = max(side_acc["btts_yes"])
    if side_acc["btts_no"]:
        out["btts_no"] = max(side_acc["btts_no"])
    if side_acc["over_1_5"]:
        out["over_1_5"] = max(side_acc["over_1_5"])
    if side_acc["under_1_5"]:
        out["under_1_5"] = max(side_acc["under_1_5"])
    if side_acc["over_2_5"]:
        out["over_2_5"] = max(side_acc["over_2_5"])
    if side_acc["under_2_5"]:
        out["under_2_5"] = max(side_acc["under_2_5"])
    if side_acc["over_3_5"]:
        out["over_3_5"] = max(side_acc["over_3_5"])
    if side_acc["under_3_5"]:
        out["under_3_5"] = max(side_acc["under_3_5"])
    return out


def _market_odds_from_side_parsed(side: Dict[str, Any]) -> Dict[str, Any]:
    """Shape parsed side dict into fixture ``market_odds`` structure."""
    market_odds: Dict[str, Any] = {}
    if side.get("btts_yes") or side.get("btts_no"):
        market_odds["btts"] = {
            k: v
            for k, v in (("yes", side.get("btts_yes")), ("no", side.get("btts_no")))
            if v
        }
    if side.get("over_2_5") or side.get("under_2_5"):
        market_odds["totals_2_5"] = {
            k: v
            for k, v in (("over", side.get("over_2_5")), ("under", side.get("under_2_5")))
            if v
        }
    if side.get("over_1_5") or side.get("under_1_5"):
        market_odds["totals_1_5"] = {
            k: v
            for k, v in (("over", side.get("over_1_5")), ("under", side.get("under_1_5")))
            if v
        }
    if side.get("over_3_5") or side.get("under_3_5"):
        market_odds["totals_3_5"] = {
            k: v
            for k, v in (("over", side.get("over_3_5")), ("under", side.get("under_3_5")))
            if v
        }
    return market_odds


def _merge_market_odds_additive(
    primary: Dict[str, Any],
    supplemental: Dict[str, Any],
) -> Dict[str, Any]:
    """Fill missing side-market prices only; never overwrite API-Sports lines."""
    out = dict(primary or {})
    for key in ("btts", "totals_2_5", "totals_1_5", "totals_3_5"):
        sub = supplemental.get(key)
        if not isinstance(sub, dict) or not sub:
            continue
        cur = out.get(key)
        if not isinstance(cur, dict):
            cur = {}
        merged = dict(cur)
        for side, val in sub.items():
            try:
                fv = float(val)
            except (TypeError, ValueError):
                continue
            if fv <= 1.0:
                continue
            if not merged.get(side):
                merged[side] = fv
        if merged:
            out[key] = merged
    return out


class DataAggregator:
    """Aggregates data from multiple APIs to enrich fixture data."""

    def __init__(self) -> None:
        _load_dotenv_from_project()
        load_dotenv()
        self.cache = Cache()
        self.clients = self._initialize_clients()
        self._team_recent_mem: Dict[str, Tuple[List[Dict[str, Any]], float]] = {}
        self._team_recent_lock = threading.Lock()
        self._api_sem = threading.Semaphore(_enrich_api_semaphore_size())
        if os.getenv("HIBS_CACHE_PRUNE", "1").lower() not in ("0", "false", "no"):
            try:
                n = self.cache.prune_stale()
                if n:
                    print(f"[Cache] Pruned {n} stale on-disk entries")
            except OSError as exc:
                print(f"[Cache] Prune skipped: {exc}")

    def _initialize_clients(self) -> Dict[str, Any]:
        clients: Dict[str, Any] = {}

        api_sports_key = _env_first_usable(
            "API_SPORTS_FOOTBALL_KEY",
            "API_SPORTS_KEY",
            "APISPORTS_KEY",
        )
        disable_api = os.getenv("HIBS_DISABLE_API_SPORTS", "").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        if api_sports_key and not disable_api:
            clients["api_sports"] = ApiSportsFootballClient(api_sports_key)
        elif not api_sports_key and not disable_api:
            print(
                "[Data] No usable API-Sports key — scrape-first mode "
                "(Football-Data + scrapers). Set HIBS_DISABLE_API_SPORTS=1 to silence."
            )

        fdo_key = _env_first_usable("FOOTBALL_DATA_ORG_KEY", "FOOTBALL_DATA_KEY")
        if fdo_key:
            clients["football_data_org"] = FootballDataOrgClient(fdo_key)

        sm_key = _env_first_usable("SPORTSMONK_KEY")
        if sm_key:
            clients["sportsmonk"] = SportsMonkClient(sm_key)

        odds_key = _env_first_usable("ODDS_API_KEY")
        if odds_key:
            clients["odds_api"] = OddsApiClient(odds_key)

        oddsp_key = _env_first_usable("ODDSPAPI_API_KEY")
        if oddsp_key:
            try:
                from hibs_predictor.ingress.oddspapi_client import OddsPapiClient, oddspapi_enabled

                ingress = (os.getenv("HIBS_ODDS_INGRESS") or "").strip().lower()
                if oddspapi_enabled() or ingress in ("oddspapi", "sharp", "oddspapi_sharp"):
                    clients["oddspapi"] = OddsPapiClient(oddsp_key)
            except ImportError:
                pass

        stats_key = _env_first_usable("STATS_API_KEY")
        if stats_key:
            clients["stats_api"] = StatsApiClient(stats_key)

        return clients

    def _fetch_api_sports_position_with_fallback(
        self, team_id: Optional[int], league_api_id: Optional[int], season: int
    ) -> Dict[str, Any]:
        if not team_id or not league_api_id or "api_sports" not in self.clients:
            return {}
        for sy in [season, season - 1]:
            row = self._fetch_team_position(team_id, league_api_id, sy)
            if row:
                row.setdefault("source", "api_sports")
                if sy != season:
                    row.setdefault("season_status", "last_completed")
                return row
        return {}

    def _fetch_football_data_position_with_fallback(
        self,
        team_id: Optional[int],
        team_name: str,
        competition_code: Optional[str],
        season: int,
    ) -> Dict[str, Any]:
        from hibs_predictor.api_clients import football_data_requests_allowed

        if not competition_code or "football_data_org" not in self.clients:
            return {}
        if not football_data_requests_allowed():
            return {}
        client = self.clients["football_data_org"]
        seasons = [season]
        if (os.getenv("HIBS_FOOTBALL_DATA_PRIOR_SEASON") or "").strip().lower() in ("1", "true", "yes", "on"):
            seasons.append(season - 1)
        for sy in seasons:
            if team_id:
                row = client.fetch_team_position(int(team_id), str(competition_code), int(sy))
                if row:
                    if sy != season:
                        row.setdefault("season_status", "last_completed")
                    return row
            try:
                groups = client.fetch_standings(str(competition_code), int(sy))
            except Exception:
                groups = []
            wanted = _norm_team_name(team_name)
            if not wanted:
                continue
            for group in groups or []:
                if str(group.get("type") or "").upper() not in ("TOTAL", ""):
                    continue
                for entry in group.get("table") or []:
                    candidate = _norm_team_name((entry.get("team") or {}).get("name"))
                    if candidate and (candidate == wanted or candidate in wanted or wanted in candidate):
                        row = _football_data_position_from_entry(entry)
                        if sy != season:
                            row.setdefault("season_status", "last_completed")
                        return row
        return {}

    def enrich_fixture(self, fixture: Dict[str, Any], league_code: str = "EPL") -> Dict[str, Any]:
        """Enrich a fixture with comprehensive data from multiple sources."""
        league = LEAGUES.get(league_code, {})
        league_api_id = league.get("api_sports_id")
        fdo_comp = league.get("football_data_org_id")
        now = datetime.now()
        season = _season_candidates(now, league_code=league_code)[0]

        home_id = fixture_team_id(fixture, "home")
        away_id = fixture_team_id(fixture, "away")
        hk = fixture_team_name(fixture, "home") or "?"
        ak = fixture_team_name(fixture, "away") or "?"
        prefer_name_ids = fixture.get("source") == "fotmob_public" or str(
            (fixture.get("fixture") or {}).get("id") if isinstance(fixture.get("fixture"), dict) else fixture.get("id")
            or ""
        ).startswith("fotmob_")

        fx = fixture.get("fixture")
        raw_fid = fx.get("id") if isinstance(fx, dict) else None
        if raw_fid is None:
            raw_fid = fixture.get("id")
        fixture_id_str = str(raw_fid).strip() if raw_fid not in (None, "", 0, "0") else ""
        dt = str(fixture.get("date", ""))
        if fixture_id_str:
            cache_key = f"enriched_fixture_{fixture_id_str}_{league_code}_dq9"
        else:
            cache_key = f"enriched_fixture_teams_{league_code}_{hk}|{ak}|{dt}_dq9"

        try:
            fixture_id_for_xg = int(raw_fid) if raw_fid not in (None, "", "0", 0) else None
        except (TypeError, ValueError):
            fixture_id_for_xg = None

        cached = self.cache.get(cache_key, ttl_hours=2)
        if cached and not self._enriched_needs_recent_refetch(cached, home_id, away_id):
            from hibs_predictor.deep_enrich import deep_enrich_plan, maybe_deep_enrich

            out = dict(cached)
            if deep_enrich_plan(fixture, league_code, out):
                try:
                    out = maybe_deep_enrich(self, fixture, league_code, out)
                    out.setdefault("league", league_code)
                    out["data_quality"] = compute_fixture_data_quality(out)
                    self.cache.set(
                        cache_key,
                        out,
                        ttl_hours=_enriched_disk_ttl_hours(fixture, out, home_id, away_id),
                    )
                except Exception as exc:
                    print(f"[enrich deep cache] {league_code} fid={fixture_id_str}: {exc!r}")
                    return cached
            return out

        if not cached:
            stale_disk = self.cache.peek(cache_key)
            if stale_disk and isinstance(stale_disk, dict):
                from hibs_predictor.data_quality import _has_stats

                if _has_stats(stale_disk.get("home_stats")) and _has_stats(stale_disk.get("away_stats")):
                    return stale_disk

        enriched = dict(cached) if cached else dict(fixture)

        league_strength = float(league.get("strength_factor", 1.0))

        stats_league_code = league_code
        stats_league_api_id = league_api_id
        if is_cup_competition(league_code):
            stats_league_code, stats_league_api_id = _cup_domestic_stats_league(league_code)

        # API team stats before recent matches so season xG can run when ids exist.
        if home_id:
            try:
                enriched["home_stats"] = self._fetch_team_stats(
                    home_id, stats_league_code, stats_league_api_id, season, {}, fdo_comp=fdo_comp
                )
            except Exception as exc:
                print(f"[enrich home_stats] {league_code} fid={fixture_id_str}: {exc!r}")
                enriched["home_stats"] = {}
        else:
            enriched.setdefault("home_stats", {})
        if away_id:
            try:
                enriched["away_stats"] = self._fetch_team_stats(
                    away_id, stats_league_code, stats_league_api_id, season, {}, fdo_comp=fdo_comp
                )
            except Exception as exc:
                print(f"[enrich away_stats] {league_code} fid={fixture_id_str}: {exc!r}")
                enriched["away_stats"] = {}
        else:
            enriched.setdefault("away_stats", {})

        if home_id and away_id:
            try:
                from hibs_predictor.scraped_xg import apply_season_team_xg_from_stats

                if apply_season_team_xg_from_stats(enriched, league_strength):
                    print(
                        f"[enrich season_team_xg] {league_code} fid={fixture_id_str} "
                        f"xg_source={enriched.get('xg_source')}"
                    )
            except Exception as exc:
                print(f"[enrich season_team_xg] {league_code} fid={fixture_id_str}: {exc!r}")

        try:
            enriched["home_recent"] = self._fetch_team_recent_matches(
                home_id,
                fdo_comp=fdo_comp,
                team_name=hk,
                prefer_name_resolution=prefer_name_ids,
                league_code=league_code,
            )
        except Exception as exc:
            print(f"[enrich home_recent] {league_code} fid={fixture_id_str}: {exc!r}")
            enriched["home_recent"] = []
        try:
            enriched["away_recent"] = self._fetch_team_recent_matches(
                away_id,
                fdo_comp=fdo_comp,
                team_name=ak,
                prefer_name_resolution=prefer_name_ids,
                league_code=league_code,
            )
        except Exception as exc:
            print(f"[enrich away_recent] {league_code} fid={fixture_id_str}: {exc!r}")
            enriched["away_recent"] = []

        try:
            home_rates = _recent_match_rates(enriched["home_recent"], home_id or 0)
            away_rates = _recent_match_rates(enriched["away_recent"], away_id or 0)
        except Exception as exc:
            print(f"[enrich match_rates] {league_code} fid={fixture_id_str}: {exc!r}")
            home_rates = _empty_rates()
            away_rates = _empty_rates()
        enriched["home_btts_rate"] = home_rates["btts_rate"]
        enriched["away_btts_rate"] = away_rates["btts_rate"]
        enriched["home_recent_n"] = int(home_rates["n"])
        enriched["away_recent_n"] = int(away_rates["n"])
        enriched["home_over25_rate"] = home_rates["over25_rate"]
        enriched["away_over25_rate"] = away_rates["over25_rate"]
        enriched["home_over15_rate"] = home_rates["over15_rate"]
        enriched["away_over15_rate"] = away_rates["over15_rate"]

        if home_id and self._team_stats_sparse(enriched.get("home_stats")):
            try:
                enriched["home_stats"] = self._fetch_team_stats(
                    home_id,
                    league_code,
                    league_api_id,
                    season,
                    home_rates,
                    fdo_comp=fdo_comp,
                    bypass_cache=True,
                )
            except Exception as exc:
                print(f"[enrich home_stats_refresh] {league_code} fid={fixture_id_str}: {exc!r}")
        if away_id and self._team_stats_sparse(enriched.get("away_stats")):
            try:
                enriched["away_stats"] = self._fetch_team_stats(
                    away_id,
                    league_code,
                    league_api_id,
                    season,
                    away_rates,
                    fdo_comp=fdo_comp,
                    bypass_cache=True,
                )
            except Exception as exc:
                print(f"[enrich away_stats_refresh] {league_code} fid={fixture_id_str}: {exc!r}")

        if home_id and away_id:
            try:
                from hibs_predictor.scraped_xg import apply_season_team_xg_from_stats

                cur = str(enriched.get("xg_source") or "").lower()
                if cur not in ("api_season_team_xg", "team_season_xg") and apply_season_team_xg_from_stats(
                    enriched, league_strength
                ):
                    print(
                        f"[enrich season_team_xg] {league_code} fid={fixture_id_str} "
                        f"xg_source={enriched.get('xg_source')} (post-recent)"
                    )
            except Exception as exc:
                print(f"[enrich season_team_xg] {league_code} fid={fixture_id_str}: {exc!r}")

        try:
            enriched["home_form"] = TeamStrengthCalculator.calculate_form_strength(
                enriched["home_recent"], home_id
            )
        except Exception as exc:
            print(f"[enrich home_form] {league_code} fid={fixture_id_str}: {exc!r}")
            enriched["home_form"] = 0.5
        try:
            enriched["away_form"] = TeamStrengthCalculator.calculate_form_strength(
                enriched["away_recent"], away_id
            )
        except Exception as exc:
            print(f"[enrich away_form] {league_code} fid={fixture_id_str}: {exc!r}")
            enriched["away_form"] = 0.5

        try:
            enriched["home_home_factor"] = TeamStrengthCalculator.calculate_home_away_factor(
                home_id, enriched["home_recent"], is_home=True
            )
        except Exception as exc:
            print(f"[enrich home_home_factor] {league_code} fid={fixture_id_str}: {exc!r}")
            enriched["home_home_factor"] = 1.0
        try:
            enriched["away_away_factor"] = TeamStrengthCalculator.calculate_home_away_factor(
                away_id, enriched["away_recent"], is_home=False
            )
        except Exception as exc:
            print(f"[enrich away_away_factor] {league_code} fid={fixture_id_str}: {exc!r}")
            enriched["away_away_factor"] = 1.0

        home_nm = fixture_team_name(fixture, "home")
        away_nm = fixture_team_name(fixture, "away")
        prefer_scraped = os.getenv("HIBS_PREFER_SCRAPED_STANDINGS", "1").lower() in ("1", "true", "yes")

        hp: Dict[str, Any] = {}
        ap: Dict[str, Any] = {}

        if league_api_id and "api_sports" in self.clients:
            skip_api_tbl = os.getenv("HIBS_SKIP_API_STANDINGS", "0").lower() in ("1", "true", "yes")
            if not skip_api_tbl:
                try:
                    if not hp.get("position"):
                        hp = self._fetch_api_sports_position_with_fallback(home_id, league_api_id, season) or hp
                except Exception as exc:
                    print(f"[enrich home_position] {league_code} fid={fixture_id_str}: {exc!r}")
                try:
                    if not ap.get("position"):
                        ap = self._fetch_api_sports_position_with_fallback(away_id, league_api_id, season) or ap
                except Exception as exc:
                    print(f"[enrich away_position] {league_code} fid={fixture_id_str}: {exc!r}")

        if fdo_comp and "football_data_org" in self.clients:
            from hibs_predictor.api_clients import football_data_requests_allowed

            if football_data_requests_allowed():
                try:
                    if not hp.get("position"):
                        hp = self._fetch_football_data_position_with_fallback(home_id, home_nm, fdo_comp, season) or hp
                except Exception as exc:
                    print(f"[enrich fdo_home_position] {league_code} fid={fixture_id_str}: {exc!r}")
                try:
                    if not ap.get("position"):
                        ap = self._fetch_football_data_position_with_fallback(away_id, away_nm, fdo_comp, season) or ap
                except Exception as exc:
                    print(f"[enrich fdo_away_position] {league_code} fid={fixture_id_str}: {exc!r}")

        if prefer_scraped and league_code in soccerstats_standings.LEAGUE_PARAM:
            try:
                if not hp.get("position") or not ap.get("position"):
                    ss_rows = self._cached_soccerstats_league_table(league_code)
                    if ss_rows:
                        if not hp.get("position"):
                            sr = soccerstats_standings.find_team_row(ss_rows, home_nm)
                            if sr:
                                hp = soccerstats_standings.row_to_position_shape(sr)
                        if not ap.get("position"):
                            sr_a = soccerstats_standings.find_team_row(ss_rows, away_nm)
                            if sr_a:
                                ap = soccerstats_standings.row_to_position_shape(sr_a)
            except Exception as exc:
                if os.getenv("HIBS_DEBUG", "0").lower() in ("1", "true", "yes"):
                    print(f"[enrich soccerstats_positions] {league_code} fid={fixture_id_str}: {exc!r}")

        enriched["home_position"] = normalize_position_dict(hp)
        enriched["away_position"] = normalize_position_dict(ap)

        season_xg_tag = str(enriched.get("xg_source") or "")
        try:
            xh, xa, xg_tag = self._fetch_expected_goals(
                fixture_id_for_xg,
                home_rates,
                away_rates,
                league_strength,
                home_team_id=home_id,
                away_team_id=away_id,
                home_name=home_nm,
                away_name=away_nm,
                allow_statistics_xg=True,
                league_code=league_code,
            )
            if xg_tag in ("api_fixture_xg", "api_statistics_xg", "stats_api_xg"):
                enriched["xg_home"], enriched["xg_away"], enriched["xg_source"] = float(xh), float(xa), xg_tag
            elif season_xg_tag not in ("api_season_team_xg", "team_season_xg"):
                enriched["xg_home"], enriched["xg_away"], enriched["xg_source"] = float(xh), float(xa), xg_tag
            elif xg_tag == "mixed_api_goals_proxy":
                enriched["xg_home"], enriched["xg_away"], enriched["xg_source"] = float(xh), float(xa), xg_tag
        except Exception as exc:
            print(f"[enrich xg] {league_code} fid={fixture_id_str}: {exc!r}")
            if season_xg_tag not in ("api_season_team_xg", "team_season_xg"):
                lam_h, lam_a = self._lambda_from_rates(home_rates, away_rates, league_strength)
                enriched["xg_home"], enriched["xg_away"], enriched["xg_source"] = float(lam_h), float(lam_a), "goals_proxy"

        if home_id and away_id:
            try:
                from hibs_predictor.scraped_xg import apply_season_team_xg_from_stats

                cur = str(enriched.get("xg_source") or "").lower()
                if cur not in ("api_season_team_xg", "team_season_xg", "api_fixture_xg", "api_statistics_xg", "stats_api_xg"):
                    if apply_season_team_xg_from_stats(enriched, league_strength):
                        print(
                            f"[enrich season_team_xg] {league_code} fid={fixture_id_str} "
                            f"xg_source={enriched.get('xg_source')} (post-fetch_xg)"
                        )
            except Exception as exc:
                print(f"[enrich season_team_xg] {league_code} fid={fixture_id_str}: {exc!r}")

        try:
            bundle = self._fetch_odds_bundle(fixture, league_code)
        except Exception as exc:
            print(f"[enrich odds_bundle] {league_code} fid={fixture_id_str}: {exc!r}")
            bundle = _empty_odds_bundle()
        enriched["odds_home"] = bundle["odds_home"]
        enriched["odds_draw"] = bundle["odds_draw"]
        enriched["odds_away"] = bundle["odds_away"]
        enriched["odds_available"] = bundle["odds_available"]
        enriched["all_bookmaker_odds"] = bundle["all_bookmaker_odds"]
        enriched["odds_secondary"] = bundle["odds_secondary"]
        enriched["odds_cross_max_implied_diff_pct"] = bundle["odds_cross_max_implied_diff_pct"]
        enriched["odds_cross_book_max_implied_diff_pct"] = bundle.get("odds_cross_book_max_implied_diff_pct", 0.0)
        enriched["odds_primary_source"] = bundle["odds_primary_source"]
        enriched["market_odds"] = bundle["market_odds"]
        enriched["best_odds_1x2"] = bundle.get("best_odds_1x2") or {}
        enriched["best_odds_source"] = bundle.get("best_odds_source") or {}
        enriched["sharp_anchor_implied"] = bundle.get("sharp_anchor_implied") or {}
        enriched["league_factor"] = league.get("strength_factor", 1.0)
        try:
            fid_int = int(raw_fid) if raw_fid not in (None, "", "0", 0) else 0
        except (TypeError, ValueError):
            fid_int = 0
        core_ready = self._core_enrich_ready(enriched, home_id, away_id)
        if core_ready and fixture_id_for_xg and "api_sports" in self.clients:
            try:
                from hibs_predictor.fixture_statistics_xg import (
                    fetch_fixture_statistics_xg,
                    needs_statistics_xg_fetch,
                )

                cur_xg = str(enriched.get("xg_source") or "")
                if needs_statistics_xg_fetch(cur_xg):
                    stats_hit = fetch_fixture_statistics_xg(
                        self.clients["api_sports"],
                        self.cache,
                        int(fixture_id_for_xg),
                        home_team_id=home_id,
                        away_team_id=away_id,
                        home_name=home_nm,
                        away_name=away_nm,
                        current_source=cur_xg,
                        league_code=league_code,
                    )
                    if stats_hit:
                        enriched["xg_home"], enriched["xg_away"], enriched["xg_source"] = (
                            float(stats_hit[0]),
                            float(stats_hit[1]),
                            str(stats_hit[2]),
                        )
            except Exception as exc:
                print(f"[enrich statistics_xg] {league_code} fid={fixture_id_str}: {exc!r}")
        if core_ready and fid_int and "api_sports" in self.clients:
            from hibs_predictor.scrape_first import skip_api_injuries

            if not skip_api_injuries():
                try:
                    enriched["fixture_injuries"] = self.clients["api_sports"].fetch_injuries(fid_int)
                except Exception:
                    enriched["fixture_injuries"] = []
            else:
                enriched.setdefault("fixture_injuries", [])
        else:
            enriched.setdefault("fixture_injuries", [])
        if core_ready:
            try:
                self._maybe_attach_player_insight(enriched, league_code, season)
            except Exception as exc:
                print(f"[enrich player_insight] {league_code} fid={fixture_id_str}: {exc!r}")
        try:
            from hibs_predictor.team_news_enrich import apply_team_news_fields

            apply_team_news_fields(enriched)
        except Exception as exc:
            print(f"[enrich team_news] {league_code} fid={fixture_id_str}: {exc!r}")
        if core_ready and fid_int and "api_sports" in self.clients:
            try:
                from hibs_predictor.squad_depth_enrich import attach_api_squad_depth

                attach_api_squad_depth(enriched, self.clients["api_sports"], season=season)
            except Exception as exc:
                print(f"[enrich squad_depth] {league_code} fid={fixture_id_str}: {exc!r}")
        if core_ready:
            try:
                from hibs_predictor.lineup_enrich import (
                    apply_lineup_fields,
                    lineup_cache_ttl_hours,
                    should_fetch_lineups,
                )

                raw_lineups = None
                if fid_int and "api_sports" in self.clients and should_fetch_lineups(
                    enriched, api_client_present=True
                ):
                    ttl = lineup_cache_ttl_hours(enriched)
                    raw_lineups = self.clients["api_sports"].fetch_fixture_lineups(fid_int, ttl_hours=ttl)
                apply_lineup_fields(enriched, raw_lineups=raw_lineups)
            except Exception as exc:
                print(f"[enrich lineup] {league_code} fid={fixture_id_str}: {exc!r}")
                try:
                    from hibs_predictor.lineup_enrich import apply_lineup_fields

                    apply_lineup_fields(enriched)
                except Exception:
                    enriched.setdefault("fixture_lineups", None)
                    enriched.setdefault("lineup_confirmed", False)
                    enriched.setdefault("lineup_meta", {})
        else:
            enriched.setdefault("fixture_lineups", None)
            enriched.setdefault("lineup_confirmed", False)
            enriched.setdefault("lineup_meta", {})
        try:
            enriched["supplemental"] = collect_supplemental(fixture, league_code, enriched)
        except Exception as exc:
            print(f"[enrich supplemental] {league_code} fid={fixture_id_str}: {exc!r}")
            enriched["supplemental"] = {}
        try:
            from hibs_predictor.team_news_enrich import apply_team_news_fields

            apply_team_news_fields(enriched)
        except Exception as exc:
            print(f"[enrich team_news supplemental] {league_code} fid={fixture_id_str}: {exc!r}")
        try:
            from hibs_predictor.scrapers.thin_data_rescue import apply_thin_data_rescue

            enriched = apply_thin_data_rescue(
                enriched,
                fixture,
                league_code,
                home_id=home_id,
                away_id=away_id,
                supplemental=enriched.get("supplemental"),
            )
        except Exception as exc:
            print(f"[enrich thin_rescue] {league_code} fid={fixture_id_str}: {exc!r}")
        try:
            from hibs_predictor.scraped_xg import apply_scraped_xg_to_enriched

            enriched = apply_scraped_xg_to_enriched(fixture, league_code, enriched)
        except Exception as exc:
            print(f"[enrich scraped_xg] {league_code} fid={fixture_id_str}: {exc!r}")
        try:
            from hibs_predictor.deep_enrich import maybe_deep_enrich

            enriched = maybe_deep_enrich(self, fixture, league_code, enriched)
        except Exception as exc:
            print(f"[enrich deep] {league_code} fid={fixture_id_str}: {exc!r}")
        enriched.setdefault("league", league_code)
        try:
            enriched["data_quality"] = compute_fixture_data_quality(enriched)
        except Exception as exc:
            print(f"[enrich data_quality] {league_code} fid={fixture_id_str}: {exc!r}")
            enriched["data_quality"] = {"score_pct": 0.0, "blocks": [], "full_scope": False, "strong_scope": False}

        try:
            from hibs_predictor.xg_source_display import attach_xg_display_fields

            attach_xg_display_fields(enriched, enriched)
        except Exception as exc:
            print(f"[enrich xg_display] {league_code} fid={fixture_id_str}: {exc!r}")

        enriched["enriched_at"] = datetime.now().isoformat()
        self.cache.set(
            cache_key,
            enriched,
            ttl_hours=_enriched_disk_ttl_hours(fixture, enriched, home_id, away_id),
        )
        return enriched

    @classmethod
    def _enriched_cache_fresh(
        cls,
        enriched: Dict[str, Any],
        home_id: Optional[int],
        away_id: Optional[int],
        *,
        minutes: Optional[float] = None,
    ) -> bool:
        """Skip full re-enrich when recently written and both sides have recent-match data."""
        if cls._enriched_needs_recent_refetch(enriched, home_id, away_id):
            return False
        ts = enriched.get("enriched_at")
        if not ts:
            return False
        try:
            at = datetime.fromisoformat(str(ts))
        except (TypeError, ValueError):
            return False
        window = timedelta(minutes=minutes if minutes is not None else _enrich_fresh_minutes())
        if datetime.now() - at > window:
            return False
        return True

    @staticmethod
    def _enriched_needs_recent_refetch(
        enriched: Dict[str, Any],
        home_id: Optional[int],
        away_id: Optional[int],
    ) -> bool:
        """True when core API inputs are missing (retry, don't freeze thin rows after 429)."""
        from hibs_predictor.data_quality import _has_stats

        if home_id and not (enriched.get("home_recent") or []):
            return True
        if away_id and not (enriched.get("away_recent") or []):
            return True
        if home_id and not _has_stats(enriched.get("home_stats")):
            return True
        if away_id and not _has_stats(enriched.get("away_stats")):
            return True
        return False

    @staticmethod
    def _team_stats_sparse(stats: Any) -> bool:
        if not isinstance(stats, dict) or not stats:
            return True
        try:
            played = int(stats.get("played") or 0)
        except (TypeError, ValueError):
            return True
        if played < 3:
            return True
        try:
            gf = float(stats.get("goals_for") or 0)
        except (TypeError, ValueError):
            gf = 0.0
        return gf <= 0 and not stats.get("api_season_xg_measured")

    @staticmethod
    def _core_enrich_ready(
        enriched: Dict[str, Any],
        home_id: Optional[int],
        away_id: Optional[int],
    ) -> bool:
        """Skip optional API calls (lineups, squad, injuries) until form + stats are loaded."""
        return not DataAggregator._enriched_needs_recent_refetch(enriched, home_id, away_id)

    def _fetch_team_stats(
        self,
        team_id: Optional[int],
        league_code: str,
        league_api_id: Optional[int] = None,
        season: int = None,
        recent_rates: Optional[Dict[str, float]] = None,
        fdo_comp: Optional[str] = None,
        *,
        bypass_cache: bool = False,
    ) -> Dict[str, Any]:
        """Fetch team statistics from API-Football; augment with recent-match aggregates when sparse."""
        recent_rates = recent_rates or {}
        if not team_id:
            return {}

        season = season or (datetime.now().year if datetime.now().month >= 7 else datetime.now().year - 1)
        cache_key = f"team_stats_{team_id}_{league_code}_{season}"
        if not bypass_cache:
            cached = self.cache.get(cache_key, ttl_hours=18)
            if cached:
                return cached

        stats: Dict[str, Any] = {}

        if "api_sports" in self.clients:
            for s in [season, season - 1]:
                try:
                    team_stats = self.clients["api_sports"].fetch_team_statistics(team_id, s, league_api_id)
                    if not team_stats:
                        continue
                    goals_for, goals_against = _extract_goals_totals_from_api_stats(team_stats)
                    shots = team_stats.get("shots", {}) or {}
                    on_blk = shots.get("on", {}) or {}
                    sot_raw = on_blk.get("total")
                    if isinstance(sot_raw, dict):
                        sot_val = int(sot_raw.get("total") or 0)
                    else:
                        try:
                            sot_val = int(sot_raw or 0)
                        except (TypeError, ValueError):
                            sot_val = 0
                    fixtures_blk = team_stats.get("fixtures", {}) or {}
                    played = fixtures_blk.get("played", {}) or {}
                    played_total = played.get("total")
                    try:
                        played_n = int(played_total or 0)
                    except (TypeError, ValueError):
                        played_n = 0
                    xg_for_t, xg_against_t = _extract_xg_totals_from_api_stats(team_stats)
                    stats = {
                        "goals_for": goals_for,
                        "goals_against": goals_against,
                        "shots_on_target": sot_val,
                        "played": played_n,
                        "wins": (fixtures_blk.get("wins", {}) or {}).get("total", 0),
                        "draws": (fixtures_blk.get("draws", {}) or {}).get("total", 0),
                        "losses": (fixtures_blk.get("loses", {}) or {}).get("total", 0),
                    }
                    if xg_for_t is not None and played_n >= 3:
                        stats["xg_for"] = float(xg_for_t)
                        if xg_against_t is not None:
                            stats["xg_against"] = float(xg_against_t)
                        stats["xg_for_pg"] = float(xg_for_t) / played_n
                        if xg_against_t is not None:
                            stats["xg_against_pg"] = float(xg_against_t) / played_n
                        stats["api_season_xg_measured"] = True
                    if goals_for or goals_against or played_n:
                        break
                except Exception:
                    continue

        if (
            (not stats or (stats.get("goals_for", 0) == 0 and stats.get("goals_against", 0) == 0))
            and fdo_comp
            and "football_data_org" in self.clients
        ):
            try:
                from hibs_predictor.api_clients import football_data_team_matches_enabled

                if not football_data_team_matches_enabled():
                    raise RuntimeError("fdo_team_matches_disabled")
                fdo_matches = self.clients["football_data_org"].fetch_team_matches(int(team_id), 10)
                fdo_stats = _stats_from_fdo_matches(fdo_matches)
                if fdo_stats.get("played"):
                    stats = fdo_stats
            except Exception:
                pass

        if (not stats or (stats.get("goals_for", 0) == 0 and stats.get("goals_against", 0) == 0)) and recent_rates.get("n", 0) >= 3:
            gf = recent_rates["avg_gf"] * 10.0
            ga = recent_rates["avg_ga"] * 10.0
            stats = {
                "goals_for": max(0.0, gf),
                "goals_against": max(0.0, ga),
                "shots_on_target": stats.get("shots_on_target", 0) if stats else 0,
                "played": int(recent_rates.get("n", 0)),
                "expected_goals": max(0.1, gf * 0.92),
                "expected_goals_against": max(0.1, ga * 0.92),
            }

        if stats and stats.get("played", 0) and stats.get("goals_for", 0) is not None:
            gp = max(1, int(stats.get("played", 1)))
            stats.setdefault("expected_goals", float(stats.get("goals_for", 0)) * 0.92)
            stats.setdefault("expected_goals_against", float(stats.get("goals_against", 0)) * 0.92)

        if _has_stats(stats):
            self.cache.set(cache_key, stats, ttl_hours=18)
        else:
            self.cache.set(cache_key, stats, ttl_hours=0.2)
        return stats

    def _maybe_attach_player_insight(
        self, enriched: Dict[str, Any], league_code: str, season: int
    ) -> None:
        """Top scorers per side (display-only; 24h league cache)."""
        if os.getenv("HIBS_ENABLE_PLAYER_INSIGHT", "").strip().lower() not in ("1", "true", "yes", "on"):
            return
        if os.getenv("HIBS_SKIP_API_PLAYER_STATS", "0").strip().lower() in ("1", "true", "yes", "on"):
            return
        league = LEAGUES.get(league_code, {})
        league_api_id = league.get("api_sports_id")
        if not league_api_id or "api_sports" not in self.clients:
            return
        home_id = enriched.get("home_id")
        away_id = enriched.get("away_id")
        try:
            rows = self.clients["api_sports"].fetch_top_scorers(int(league_api_id), int(season))
        except Exception:
            rows = []
        if not rows:
            return

        def _goals(entry: Dict[str, Any]) -> int:
            stats = entry.get("statistics") or []
            if not stats:
                return 0
            g = (stats[0] or {}).get("goals") or {}
            try:
                return int(g.get("total") or 0)
            except (TypeError, ValueError):
                return 0

        def _team_top(team_id: Optional[int], limit: int = 3) -> List[Dict[str, Any]]:
            if not team_id:
                return []
            out: List[Dict[str, Any]] = []
            for entry in rows:
                if not isinstance(entry, dict):
                    continue
                stats = entry.get("statistics") or []
                tid = None
                if stats and isinstance(stats[0], dict):
                    tid = (stats[0].get("team") or {}).get("id")
                try:
                    if int(tid or 0) != int(team_id):
                        continue
                except (TypeError, ValueError):
                    continue
                pl = entry.get("player") or {}
                name = str(pl.get("name") or "").strip()
                if not name:
                    continue
                out.append({"name": name, "goals": _goals(entry)})
            out.sort(key=lambda r: -(r.get("goals") or 0))
            return out[:limit]

        enriched["home_top_scorers"] = _team_top(home_id)
        enriched["away_top_scorers"] = _team_top(away_id)

    def _fetch_team_position(self, team_id: Optional[int], league_api_id: int, season: int) -> Dict[str, Any]:
        """Fetch team's current league position."""
        if not team_id or not league_api_id:
            return {}
        try:
            if "api_sports" in self.clients:
                return self.clients["api_sports"].fetch_team_position(team_id, league_api_id, season)
        except Exception:
            pass
        return {}

    def _cached_soccerstats_league_table(self, league_code: str) -> List[Dict[str, Any]]:
        cache_key = f"soccerstats_table_{league_code}"
        cached = self.cache.get(cache_key, ttl_hours=12)
        if cached:
            return cached
        rows = soccerstats_standings.fetch_league_table(league_code, cache=self.cache)
        self.cache.set(cache_key, rows, ttl_hours=12)
        return rows

    def _team_recent_mem_get(self, mem_key: str) -> Optional[List[Dict[str, Any]]]:
        with self._team_recent_lock:
            hit = self._team_recent_mem.get(mem_key)
            if hit and hit[1] > time.monotonic():
                return hit[0]
        return None

    def _team_recent_mem_set(self, mem_key: str, matches: List[Dict[str, Any]]) -> None:
        exp = time.monotonic() + _team_recent_mem_ttl_sec()
        with self._team_recent_lock:
            self._team_recent_mem[mem_key] = (matches, exp)

    def _recent_team_ids_to_try(
        self,
        team_id: Optional[int],
        team_name: Optional[str],
        *,
        prefer_name_resolution: bool = False,
    ) -> List[int]:
        """Ordered API team ids to query for recent form (FotMob/FDO ids are often not API ids)."""
        ids: List[int] = []
        seen: set[int] = set()

        def add(raw: Any) -> None:
            try:
                tid = int(raw)
            except (TypeError, ValueError):
                return
            if tid > 0 and tid not in seen:
                seen.add(tid)
                ids.append(tid)

        resolved: Optional[int] = None
        if team_name and "api_sports" in self.clients:
            client = self.clients["api_sports"]
            if hasattr(client, "resolve_team_id_by_name"):
                try:
                    resolved = client.resolve_team_id_by_name(team_name)
                except Exception:
                    resolved = None

        if prefer_name_resolution and resolved:
            add(resolved)
        if team_id:
            add(team_id)
        if not prefer_name_resolution and resolved:
            add(resolved)
        return ids

    def _fetch_team_recent_matches(
        self,
        team_id: Optional[int],
        limit: int = 10,
        fdo_comp: Optional[str] = None,
        *,
        team_name: Optional[str] = None,
        prefer_name_resolution: bool = False,
        league_code: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Last finished matches: API-Sports first (resolve id by name when needed); FDO fallback."""
        ids_to_try = self._recent_team_ids_to_try(
            team_id,
            team_name,
            prefer_name_resolution=prefer_name_resolution,
        )
        if not ids_to_try and not team_id:
            return []

        cache_providers = ("api", "fdo") if fdo_comp else ("api",)
        for try_id in ids_to_try or ([int(team_id)] if team_id else []):
            for provider in cache_providers:
                cache_key = f"team_recent_{provider}_{try_id}"
                mem_hit = self._team_recent_mem_get(cache_key)
                if mem_hit is not None:
                    return mem_hit
                cached = self.cache.get(cache_key, ttl_hours=4)
                if cached:
                    self._team_recent_mem_set(cache_key, cached)
                    return cached

        with self._api_sem:
            for try_id in ids_to_try or ([int(team_id)] if team_id else []):
                for provider in cache_providers:
                    cache_key = f"team_recent_{provider}_{try_id}"
                    mem_hit = self._team_recent_mem_get(cache_key)
                    if mem_hit is not None:
                        return mem_hit
                    disk_again = self.cache.get(cache_key, ttl_hours=4)
                    if disk_again:
                        self._team_recent_mem_set(cache_key, disk_again)
                        return disk_again

                matches: List[Dict[str, Any]] = []
                provider = "api"
                if "api_sports" in self.clients:
                    try:
                        matches = self.clients["api_sports"].fetch_team_last_matches(try_id, limit=limit)
                    except Exception:
                        pass

                if not matches and fdo_comp and "football_data_org" in self.clients:
                    from hibs_predictor.api_clients import football_data_team_matches_enabled

                    if football_data_team_matches_enabled():
                        provider = "fdo"
                        try:
                            raw = self.clients["football_data_org"].fetch_team_matches(int(try_id), limit)
                            for m in raw or []:
                                norm = _fdo_match_to_recent_format(m)
                                if norm:
                                    matches.append(norm)
                        except Exception:
                            pass

                if not matches and team_name:
                    try:
                        from hibs_predictor.scrapers.thin_data_rescue import fotmob_recent_enabled

                        if fotmob_recent_enabled():
                            from hibs_predictor.scrapers import fotmob_client as fm

                            lc = str(league_code or "").strip().upper()
                            if lc:
                                matches = fm.team_recent_from_fotmob_calendar(
                                    lc, team_name, limit=limit
                                )
                                if matches:
                                    provider = "fotmob"
                    except Exception:
                        pass

                if provider == "fotmob" and team_name and league_code:
                    cache_key = f"team_recent_fotmob_{league_code}_{_norm_team_name(team_name)}"
                else:
                    cache_key = f"team_recent_{provider}_{try_id}"
                if matches:
                    self.cache.set(cache_key, matches, ttl_hours=4)
                    self._team_recent_mem_set(cache_key, matches)
                    return matches

            cache_key = f"team_recent_api_{ids_to_try[0] if ids_to_try else team_id}"
            self._team_recent_mem_set(cache_key, [])
            return []

    def _fetch_expected_goals(
        self,
        fixture_id: Optional[int],
        home_rates: Dict[str, float],
        away_rates: Dict[str, float],
        league_strength: float,
        *,
        home_team_id: Optional[int] = None,
        away_team_id: Optional[int] = None,
        home_name: Optional[str] = None,
        away_name: Optional[str] = None,
        allow_statistics_xg: bool = False,
        league_code: Optional[str] = None,
    ) -> Tuple[float, float, str]:
        """Expected goals from APIs; fall back to attack vs defence estimates from recent real results.

        Returns (xg_home, xg_away, source_tag) where source_tag is one of:
        api_fixture_xg, api_statistics_xg, stats_api_xg, mixed_api_goals_proxy, goals_proxy.
        """
        if not fixture_id:
            h, a = self._lambda_from_rates(home_rates, away_rates, league_strength)
            return (h, a, "goals_proxy")

        cache_key = f"xg_data_v2_{fixture_id}"
        cached = self.cache.get(cache_key, ttl_hours=6)
        if isinstance(cached, (list, tuple)) and len(cached) >= 3:
            return float(cached[0]), float(cached[1]), str(cached[2])

        xg_home: Optional[float] = None
        xg_away: Optional[float] = None
        from_stats_api = False
        filled_via_api_fixture = False

        if "stats_api" in self.clients and not _effective_skip_rapid_stats_xg(self.clients):
            try:
                xg_data = self.clients["stats_api"].fetch_xg_data(fixture_id)
                resp = xg_data.get("response") if isinstance(xg_data, dict) else None
                if resp:
                    for stat in resp:
                        tname = (stat.get("team", {}) or {}).get("name", "")
                        stats_list = stat.get("statistics") or []
                        val_raw = stats_list[0].get("value") if stats_list else None
                        try:
                            val = float(val_raw)
                        except (TypeError, ValueError):
                            continue
                        if tname == "Home":
                            xg_home = val
                        else:
                            xg_away = val
                    if (
                        xg_home is not None
                        and xg_away is not None
                        and float(xg_home) > 0
                        and float(xg_away) > 0
                    ):
                        from_stats_api = True
            except Exception:
                pass

        hid_fixture: Optional[int] = None
        aid_fixture: Optional[int] = None
        if "api_sports" in self.clients:
            try:
                fixture_data = self.clients["api_sports"].fetch_fixture(int(fixture_id))
                teams = fixture_data.get("teams") or {}
                hid_fixture = (teams.get("home") or {}).get("id")
                aid_fixture = (teams.get("away") or {}).get("id")
                stats_list = fixture_data.get("statistics") or []
                if len(stats_list) >= 2:
                    for block in stats_list:
                        team = block.get("team", {}) or {}
                        tid = team.get("id")
                        xg_block = block.get("expected_goals") or {}
                        raw = xg_block.get("value") or xg_block.get("total")
                        if raw is None:
                            continue
                        try:
                            val = float(raw)
                        except (TypeError, ValueError):
                            continue
                        if tid == hid_fixture:
                            xg_home = val
                            filled_via_api_fixture = True
                        else:
                            xg_away = val
                            filled_via_api_fixture = True
            except Exception:
                pass

        if (
            xg_home is not None
            and xg_away is not None
            and float(xg_home) > 0
            and float(xg_away) > 0
        ):
            if filled_via_api_fixture:
                tag = "api_fixture_xg"
            elif from_stats_api:
                tag = "stats_api_xg"
            else:
                tag = "mixed_api_goals_proxy"
            result = (float(xg_home), float(xg_away), tag)
            self.cache.set(cache_key, result, ttl_hours=6)
            return result

        # Do not treat API zeros as measured fixture xG (lets season-team xG remain).
        if xg_home is not None and xg_away is not None and float(xg_home) <= 0 and float(xg_away) <= 0:
            xg_home = None
            xg_away = None
            filled_via_api_fixture = False
            from_stats_api = False

        if allow_statistics_xg and "api_sports" in self.clients:
            try:
                from hibs_predictor.fixture_statistics_xg import fetch_fixture_statistics_xg

                prior = "goals_proxy"
                if (xg_home is not None and xg_home > 0) or (xg_away is not None and xg_away > 0):
                    prior = "mixed_api_goals_proxy"
                stats_hit = fetch_fixture_statistics_xg(
                    self.clients["api_sports"],
                    self.cache,
                    int(fixture_id),
                    home_team_id=home_team_id or hid_fixture,
                    away_team_id=away_team_id or aid_fixture,
                    home_name=home_name,
                    away_name=away_name,
                    current_source=prior,
                    league_code=league_code,
                )
                if stats_hit:
                    result = stats_hit
                    self.cache.set(cache_key, result, ttl_hours=6)
                    return result
            except Exception:
                pass

        est_h, est_a = self._lambda_from_rates(home_rates, away_rates, league_strength)
        use_h = xg_home if xg_home and xg_home > 0 else est_h
        use_a = xg_away if xg_away and xg_away > 0 else est_a
        had_any = (xg_home is not None and xg_home > 0) or (xg_away is not None and xg_away > 0)
        tag = "mixed_api_goals_proxy" if had_any else "goals_proxy"
        out = (float(use_h), float(use_a), tag)
        self.cache.set(cache_key, out, ttl_hours=6)
        return out

    @staticmethod
    def _lambda_from_rates(home_rates: Dict[str, float], away_rates: Dict[str, float], league_strength: float) -> Tuple[float, float]:
        """Derive Poisson lambdas from recent goals (real matches) when API xG is unavailable."""
        base = 1.15 * max(0.55, min(1.45, float(league_strength or 1.0)))
        hgf = home_rates.get("avg_gf") or 0.0
        hga = home_rates.get("avg_ga") or 0.0
        agf = away_rates.get("avg_gf") or 0.0
        aga = away_rates.get("avg_ga") or 0.0
        if home_rates.get("n", 0) < 2 and away_rates.get("n", 0) < 2:
            return base * 1.1, base * 0.95
        lam_h = max(0.35, min(3.8, (hgf + aga) / 2.0 * (0.85 + 0.15 * float(league_strength or 1.0))))
        lam_a = max(0.35, min(3.8, (agf + hga) / 2.0 * (0.85 + 0.15 * float(league_strength or 1.0))))
        return lam_h, lam_a

    def _fetch_odds_bundle(self, fixture: Dict[str, Any], league_code: str) -> Dict[str, Any]:
        """Primary + secondary 1X2 sources, cross-implied delta, and side markets from API-Football."""
        fixture_id = fixture.get("fixture", {}).get("id")
        home_name = (fixture_team_name(fixture, "home") or "").lower()
        away_name = (fixture_team_name(fixture, "away") or "").lower()

        cache_key = f"odds_bundle_{fixture_id}_{league_code}"
        cached = self.cache.get(cache_key, ttl_hours=1)
        if isinstance(cached, dict):
            return cached

        oa_home = oa_draw = oa_away = None
        op_home = op_draw = op_away = None
        as_home = as_draw = as_away = None
        all_bookmakers: List = []
        api_odds_raw: List[Dict[str, Any]] = []
        oa_side: Dict[str, Any] = {}
        oddspapi_panel: List[Dict[str, Any]] = []

        if "oddspapi" in self.clients:
            try:
                from hibs_predictor.ingress.oddspapi_client import oddspapi_enabled

                if oddspapi_enabled():
                    events = self.clients["oddspapi"].fetch_odds_for_league(league_code)
                    home_display = fixture_team_name(fixture, "home")
                    away_display = fixture_team_name(fixture, "away")
                    for event in events or []:
                        if not _odds_event_matches_fixture(
                            event, fixture, home_display, away_display
                        ):
                            continue
                        swapped = _odds_teams_swapped(
                            home_display,
                            away_display,
                            str(event.get("home_team") or ""),
                            str(event.get("away_team") or ""),
                        )
                        for row in event.get("_oddspapi_panel") or []:
                            bm_odds = dict(row)
                            if swapped and bm_odds.get("home") and bm_odds.get("away"):
                                bm_odds["home"], bm_odds["away"] = bm_odds["away"], bm_odds["home"]
                            oddspapi_panel.append(bm_odds)
                            all_bookmakers.append(bm_odds)
                        homes = [float(r["home"]) for r in oddspapi_panel if r.get("home")]
                        draws = [float(r["draw"]) for r in oddspapi_panel if r.get("draw")]
                        aways = [float(r["away"]) for r in oddspapi_panel if r.get("away")]
                        if homes:
                            op_home = max(homes)
                        if draws:
                            op_draw = max(draws)
                        if aways:
                            op_away = max(aways)
                        if op_home and op_draw and op_away:
                            break
            except Exception:
                pass

        if "odds_api" in self.clients and not _effective_skip_odds_api(self.clients):
            try:
                events = self.clients["odds_api"].fetch_odds_for_league(league_code)
                home_display = fixture_team_name(fixture, "home")
                away_display = fixture_team_name(fixture, "away")
                for event in events or []:
                    if not _odds_event_matches_fixture(
                        event, fixture, home_display, away_display
                    ):
                        continue
                    swapped = _odds_teams_swapped(
                        home_display,
                        away_display,
                        str(event.get("home_team") or ""),
                        str(event.get("away_team") or ""),
                    )
                    home_odds_list, draw_odds_list, away_odds_list = [], [], []
                    side_acc: Dict[str, List[float]] = {
                        "btts_yes": [],
                        "btts_no": [],
                        "over_1_5": [],
                        "under_1_5": [],
                        "over_2_5": [],
                        "under_2_5": [],
                        "over_3_5": [],
                        "under_3_5": [],
                    }
                    for bm in event.get("bookmakers", []) or []:
                        bm_name = _odds_bookmaker_display_name(bm)
                        bm_odds: Dict[str, Any] = {"bookmaker": bm_name, "source": "the_odds_api"}
                        _odds_api_apply_markets_to_book_row(
                            bm,
                            bm_odds,
                            home_display=home_display,
                            away_display=away_display,
                            teams_swapped=swapped,
                            side_acc=side_acc,
                        )
                        if bm_odds.get("home"):
                            home_odds_list.append(float(bm_odds["home"]))
                        if bm_odds.get("draw"):
                            draw_odds_list.append(float(bm_odds["draw"]))
                        if bm_odds.get("away"):
                            away_odds_list.append(float(bm_odds["away"]))
                        if len(bm_odds) > 1:
                            all_bookmakers.append(bm_odds)
                    if home_odds_list:
                        oa_home = max(home_odds_list)
                    if draw_odds_list:
                        oa_draw = max(draw_odds_list)
                    if away_odds_list:
                        oa_away = max(away_odds_list)
                    oa_side = _parse_odds_api_event_side_markets(event)
                    if not oa_side and side_acc:
                        oa_side = {
                            k: max(v)
                            for k, v in side_acc.items()
                            if v
                        }
                    if oa_home and oa_draw and oa_away:
                        break
            except Exception:
                pass

        if "api_sports" in self.clients and fixture_id:
            try:
                api_odds_raw = self.clients["api_sports"].fetch_odds(int(fixture_id))
                if api_odds_raw:
                    for entry in api_odds_raw:
                        for bm in entry.get("bookmakers", []) or []:
                            bets = bm.get("bets", []) or []
                            for bet in bets:
                                if bet.get("name") != "Match Winner":
                                    continue
                                values = bet.get("values", []) or []
                                bm_entry = {"bookmaker": bm.get("name", ""), "source": "api_sports"}
                                for v in values:
                                    val = (v.get("value") or "").lower()
                                    try:
                                        price = float(v.get("odd", 0) or 0)
                                    except (TypeError, ValueError):
                                        continue
                                    if price <= 1.0:
                                        continue
                                    if val == "home":
                                        bm_entry["home"] = price
                                        as_home = price if as_home is None else max(as_home, price)
                                    elif val == "draw":
                                        bm_entry["draw"] = price
                                        as_draw = price if as_draw is None else max(as_draw, price)
                                    elif val == "away":
                                        bm_entry["away"] = price
                                        as_away = price if as_away is None else max(as_away, price)
                                if len(bm_entry) > 1:
                                    all_bookmakers.append(bm_entry)
            except Exception:
                pass

        side = _parse_api_sports_side_markets(api_odds_raw)
        market_odds = _market_odds_from_side_parsed(side)
        market_odds = _merge_market_odds_additive(market_odds, _market_odds_from_side_parsed(oa_side))

        as_ok = bool(as_home and as_draw and as_away and as_home > 1 and as_draw > 1 and as_away > 1)
        oa_ok = bool(oa_home and oa_draw and oa_away and oa_home > 1 and oa_draw > 1 and oa_away > 1)
        op_ok = bool(op_home and op_draw and op_away and op_home > 1 and op_draw > 1 and op_away > 1)
        cross = 0.0
        if op_ok:
            ph, pd, pa = op_home, op_draw, op_away
            sh, sd, sa = as_home or oa_home, as_draw or oa_draw, as_away or oa_away
            primary_src = "oddspapi"
            if as_ok:
                cross = max(
                    cross,
                    _max_implied_delta_pct(as_home, as_draw, as_away, op_home, op_draw, op_away),
                )
        elif as_ok and oa_ok:
            cross = _max_implied_delta_pct(as_home, as_draw, as_away, oa_home, oa_draw, oa_away)
            ph, pd, pa = max(as_home, oa_home), max(as_draw, oa_draw), max(as_away, oa_away)
            sh, sd, sa = oa_home, oa_draw, oa_away
            primary_src = "merged_best"
        elif as_ok:
            ph, pd, pa = as_home, as_draw, as_away
            sh, sd, sa = oa_home, oa_draw, oa_away
            primary_src = "api_sports"
        elif oa_ok:
            ph, pd, pa = oa_home, oa_draw, oa_away
            sh, sd, sa = as_home, as_draw, as_away
            primary_src = "the_odds_api"
        else:
            ph = as_home if as_home else oa_home
            pd = as_draw if as_draw else oa_draw
            pa = as_away if as_away else oa_away
            sh = oa_home if ph == as_home and oa_home else (as_home if ph == oa_home and as_home else None)
            sd = oa_draw if pd == as_draw and oa_draw else (as_draw if pd == oa_draw and as_draw else None)
            sa = oa_away if pa == as_away and oa_away else (as_away if pa == oa_away and as_away else None)
            primary_src = "partial"

        line_shop = compute_best_line_from_bookmakers(all_bookmakers)
        best_1x2 = line_shop.get("best_odds_1x2") or {}
        bh = best_1x2.get("home")
        bd = best_1x2.get("draw")
        ba = best_1x2.get("away")
        best_ok = bool(bh and bd and ba and bh > 1 and bd > 1 and ba > 1)
        if best_ok:
            ph, pd, pa = bh, bd, ba
            primary_src = "line_shop_best"
        cross_book = float(line_shop.get("odds_cross_book_max_implied_diff_pct") or 0.0)
        cross = max(float(cross), cross_book)

        avail = bool(ph and pd and pa and ph > 1 and pd > 1 and pa > 1)
        all_bookmakers = _normalize_bookmaker_odds_rows(all_bookmakers)
        bundle = {
            "odds_home": ph,
            "odds_draw": pd,
            "odds_away": pa,
            "odds_available": avail,
            "all_bookmaker_odds": all_bookmakers,
            "odds_secondary": {"home": sh, "draw": sd, "away": sa},
            "odds_cross_max_implied_diff_pct": cross,
            "odds_cross_book_max_implied_diff_pct": cross_book,
            "odds_primary_source": primary_src,
            "market_odds": market_odds,
            "best_odds_1x2": line_shop.get("best_odds_1x2"),
            "best_odds_source": line_shop.get("best_odds_source"),
            "sharp_anchor_implied": line_shop.get("sharp_anchor_implied") or {},
        }
        if oddspapi_panel:
            try:
                from hibs_predictor.ingress.price_truth_ingress import panel_to_price_truth_seed

                bundle.update(panel_to_price_truth_seed(oddspapi_panel))
            except Exception:
                pass
        try:
            from hibs_predictor.scrapers.odds_thin_rescue import apply_odds_thin_rescue

            bundle = apply_odds_thin_rescue(self, fixture, league_code, bundle)
        except Exception:
            pass
        self.cache.set(cache_key, bundle, ttl_hours=1)
        return bundle

    def get_all_clients(self) -> Dict[str, Any]:
        """Return all initialized API clients."""
        return self.clients
