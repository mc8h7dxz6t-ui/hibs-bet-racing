"""Historic-data tweaks: audit Brier shrink, form weight, H2H, xG tier, bet confidence."""

from __future__ import annotations

import json
import math
import os
from typing import Any, Dict, List, Optional, Tuple

_BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DEFAULT_CALIB_CACHE = os.path.join(_BASE, ".cache", "calibration_v1.json")

# Per-team typical xG when proxy sources are used (shrink toward league pace).
_LEAGUE_AVG_XG_PER_TEAM: Dict[str, float] = {
    "EPL": 1.38,
    "CHAMPIONSHIP": 1.32,
    "LEAGUE_ONE": 1.28,
    "LEAGUE_TWO": 1.26,
    "SCOTLAND": 1.30,
    "SCOTLAND_CHAMP": 1.24,
    "LA_LIGA": 1.34,
    "SERIE_A": 1.32,
    "BUNDESLIGA": 1.40,
    "LIGUE_1": 1.33,
}
_DEFAULT_LEAGUE_AVG_XG = 1.28

_PROXY_XG_MARKERS = (
    "goals_proxy",
    "form_derived",
    "fbref_avg",
    "statsbomb_goals",
    "fotmob_league",
)


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def calibration_cache_path() -> str:
    return (os.getenv("HIBS_CALIBRATION_CACHE") or _DEFAULT_CALIB_CACHE).strip()


def xg_quality_tier(xg_source: Any) -> str:
    """high = measured xG feeds; low = goals/form proxies."""
    s = str(xg_source or "").lower()
    if not s or s == "unknown":
        return "low"
    if "understat" in s and "proxy" not in s:
        return "high"
    if any(m in s for m in ("api_fixture_xg", "api_statistics_xg", "api_xg", "stats_api_xg", "stats_api")):
        return "high"
    if any(m in s for m in ("scraped_recent", "api_season_team")):
        return "high"
    if "api" in s and "xg" in s and "proxy" not in s:
        return "high"
    if "fotmob_league" in s:
        return "medium"
    if any(m in s for m in _PROXY_XG_MARKERS) or "proxy" in s:
        return "low"
    return "medium"


def is_proxy_xg_source(xg_source: Any) -> bool:
    return xg_quality_tier(xg_source) == "low"


def league_avg_xg_per_team(league_code: str) -> float:
    return float(_LEAGUE_AVG_XG_PER_TEAM.get((league_code or "").upper(), _DEFAULT_LEAGUE_AVG_XG))


def measured_xg_lambda_scale(xg_source: Any) -> float:
    """
    Optional nudge for calibrated Poisson λ when xG is measured (not proxy).

    Off by default (`HIBS_MEASURED_XG_LAMBDA_BOOST=0`). Values 0.01–0.03 slightly
    widen λ spread for high-trust xG without changing proxy paths.
    """
    if is_proxy_xg_source(xg_source):
        return 1.0
    if xg_quality_tier(xg_source) != "high":
        return 1.0
    try:
        boost = float(os.getenv("HIBS_MEASURED_XG_LAMBDA_BOOST", "0"))
    except ValueError:
        boost = 0.0
    boost = max(0.0, min(0.03, boost))
    if boost <= 0:
        return 1.0
    return 1.0 + boost


def adjust_xg_for_source_quality(
    xg_home: float,
    xg_away: float,
    xg_source: Any,
    league_code: str,
) -> Tuple[float, float, Dict[str, Any]]:
    """Shrink proxy xG 15% toward league-average pace (Poisson λ trust)."""
    dbg: Dict[str, Any] = {"tier": xg_quality_tier(xg_source), "adjusted": False}
    scale = measured_xg_lambda_scale(xg_source)
    if scale > 1.0:
        avg = league_avg_xg_per_team(league_code)
        xh = float(xg_home)
        xa = float(xg_away)
        xg_home = xh + (xh - avg) * (scale - 1.0)
        xg_away = xa + (xa - avg) * (scale - 1.0)
        dbg["measured_lambda_scale"] = scale
        dbg["adjusted"] = True
    if not is_proxy_xg_source(xg_source):
        return xg_home, xg_away, dbg
    try:
        w = float(os.getenv("HIBS_PROXY_XG_LEAGUE_SHRINK", "0.15"))
    except ValueError:
        w = 0.15
    w = max(0.0, min(0.35, w))
    avg = league_avg_xg_per_team(league_code)
    xh = float(xg_home) * (1.0 - w) + avg * w
    xa = float(xg_away) * (1.0 - w) + avg * w
    dbg["adjusted"] = True
    dbg["shrink_weight"] = w
    dbg["league_avg_xg"] = avg
    return xh, xa, dbg


def form_sample_weight(n_home: int, n_away: int) -> float:
    """Scale form-driven signals by recent sample depth (0.4–1.0)."""
    n = min(int(n_home or 0), int(n_away or 0))
    return max(0.4, min(1.0, n / 10.0))


def apply_form_weight_to_features(
    features: List[float],
    metadata: Dict[str, Any],
    weight: float,
) -> List[float]:
    """Indices 6–9: home_form, away_form, home_home_factor, away_away_factor."""
    if weight >= 0.999:
        return features
    out = list(features)
    for idx in (6, 7, 8, 9):
        if idx < len(out):
            base = float(out[idx])
            out[idx] = 0.5 + (base - 0.5) * weight
    meta_w = max(0.4, weight)
    metadata["home_form"] = 0.5 + (float(metadata.get("home_form", 0.5)) - 0.5) * meta_w
    metadata["away_form"] = 0.5 + (float(metadata.get("away_form", 0.5)) - 0.5) * meta_w
    return out


def _team_id_from_fixture_side(side: Any) -> Optional[int]:
    if isinstance(side, dict):
        try:
            return int(side.get("id") or 0) or None
        except (TypeError, ValueError):
            return None
    return None


def _opponent_id_in_match(match: Dict[str, Any], team_id: int) -> Optional[int]:
    teams = match.get("teams") or {}
    hid = (teams.get("home") or {}).get("id")
    aid = (teams.get("away") or {}).get("id")
    try:
        hid_i = int(hid) if hid is not None else None
        aid_i = int(aid) if aid is not None else None
    except (TypeError, ValueError):
        return None
    if hid_i == team_id:
        return aid_i
    if aid_i == team_id:
        return hid_i
    return None


def _match_outcome_for_team(match: Dict[str, Any], team_id: int) -> Optional[str]:
    teams = match.get("teams") or {}
    goals = match.get("goals") or {}
    try:
        hg = int(goals.get("home"))
        ag = int(goals.get("away"))
    except (TypeError, ValueError):
        return None
    hid = (teams.get("home") or {}).get("id")
    try:
        is_home = int(hid) == int(team_id)
    except (TypeError, ValueError):
        return None
    if is_home:
        if hg > ag:
            return "home"
        if hg < ag:
            return "away"
        return "draw"
    if ag > hg:
        return "home"
    if ag < hg:
        return "away"
    return "draw"


def extract_h2h_from_recent(
    fixture: Dict[str, Any],
    max_games: int = 10,
) -> Dict[str, Any]:
    """Derive head-to-head W/D/L from stored recent match lists when teams met before."""
    home_id = _team_id_from_fixture_side(fixture.get("home"))
    away_id = _team_id_from_fixture_side(fixture.get("away"))
    if not home_id or not away_id:
        return {"n": 0, "home_wins": 0, "draws": 0, "away_wins": 0, "probs": None}

    seen: set = set()
    home_w = draw = away_w = 0

    def _scan(matches: List[Dict[str, Any]], perspective_home_id: int) -> None:
        nonlocal home_w, draw, away_w
        for m in matches or []:
            fid = (m.get("fixture") or {}).get("id") or m.get("id")
            if fid is not None:
                key = int(fid) if str(fid).isdigit() else str(fid)
                if key in seen:
                    continue
            opp = _opponent_id_in_match(m, perspective_home_id)
            if opp is None:
                continue
            if int(opp) != away_id and int(opp) != home_id:
                continue
            if fid is not None:
                seen.add(key)
            oc = _match_outcome_for_team(m, perspective_home_id)
            if oc is None:
                continue
            if perspective_home_id == home_id:
                if oc == "home":
                    home_w += 1
                elif oc == "draw":
                    draw += 1
                else:
                    away_w += 1
            else:
                if oc == "home":
                    away_w += 1
                elif oc == "draw":
                    draw += 1
                else:
                    home_w += 1

    _scan(fixture.get("home_recent") or [], home_id)
    _scan(fixture.get("away_recent") or [], away_id)
    n = home_w + draw + away_w
    probs = None
    if n > 0:
        probs = {
            "home": home_w / n,
            "draw": draw / n,
            "away": away_w / n,
        }
    return {"n": n, "home_wins": home_w, "draws": draw, "away_wins": away_w, "probs": probs}


def blend_h2h_into_1x2(
    probs: Dict[str, float],
    h2h: Dict[str, Any],
    *,
    max_shift: float = 0.05,
    min_games: int = 3,
) -> Tuple[Dict[str, float], Optional[Dict[str, Any]]]:
    """Blend historic H2H empirical 1X2 into model probs (cap 5% mass shift)."""
    n = int(h2h.get("n") or 0)
    h2h_p = h2h.get("probs")
    if n < min_games or not isinstance(h2h_p, dict):
        return probs, None
    try:
        w = float(os.getenv("HIBS_H2H_BLEND_WEIGHT", str(max_shift)))
    except ValueError:
        w = max_shift
    w = max(0.0, min(max_shift, w * min(1.0, n / 6.0)))
    out = dict(probs)
    for k in ("home", "draw", "away"):
        out[k] = float(out.get(k, 0.0)) * (1.0 - w) + float(h2h_p.get(k, 0.0)) * w
    t = sum(out.values())
    if t > 0:
        out = {k: max(1e-6, v / t) for k, v in out.items()}
    dbg = {"n_h2h": n, "blend_weight": round(w, 4), "h2h_probs": {k: round(h2h_p[k], 3) for k in h2h_p}}
    return out, dbg


def _clamp_shrink(m: float, *, league_code: str = "") -> float:
    floor = 0.88 if (league_code or "").upper() == "CHAMPIONSHIP" else 0.92
    return max(floor, min(1.08, m))


def _championship_calibration_shrink(shrink: float) -> float:
    """Extra conservative pull for volatile EFL Championship (env HIBS_CHAMPIONSHIP_CALIB_SHRINK, default 0.88)."""
    try:
        target = float(os.getenv("HIBS_CHAMPIONSHIP_CALIB_SHRINK", "0.88"))
    except ValueError:
        target = 0.88
    return min(float(shrink), max(0.85, min(0.92, target)))


def shrink_multiplier_from_brier(league_brier: float, baseline_brier: float, *, league_code: str = "") -> float:
    """Map league Brier vs baseline to calibration_shrink in [0.92, 1.08] (Championship floor 0.88)."""
    if baseline_brier <= 0:
        return 1.0
    delta = league_brier - baseline_brier
    try:
        sens = float(os.getenv("HIBS_CALIB_BRIER_SENSITIVITY", "2.5"))
    except ValueError:
        sens = 2.5
    shrink = _clamp_shrink(1.0 - delta * sens, league_code=league_code)
    if (league_code or "").upper() == "CHAMPIONSHIP":
        shrink = _championship_calibration_shrink(shrink)
    return shrink


def apply_calibration_shrink(
    probs: Dict[str, float],
    shrink: float,
) -> Dict[str, float]:
    """Pull 1X2 toward uniform when shrink<1; slightly sharpen when shrink>1."""
    s = _clamp_shrink(float(shrink))
    uniform = 1.0 / 3.0
    out = {k: float(probs.get(k, 0.0)) * s + uniform * (1.0 - s) for k in ("home", "draw", "away")}
    if s > 1.0:
        fav = max(out, key=out.get)
        excess = s - 1.0
        out[fav] = min(0.92, out[fav] + excess * 0.5)
        others = [k for k in out if k != fav]
        for k in others:
            out[k] = max(1e-6, out[k] - excess * 0.25)
    t = sum(out.values())
    if t <= 0:
        return probs
    return {k: max(1e-6, v / t) for k, v in out.items()}


def load_calibration_payload() -> Dict[str, Any]:
    """Load full calibration cache JSON (shrink, rho, ML isotonic knots)."""
    path = calibration_cache_path()
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def _clamp_rho(rho: float) -> float:
    """Institutional bounds until full per-league MLE (Dixon–Coles τ must stay positive)."""
    return max(-0.25, min(0.05, float(rho)))


def _match_style_rho_scale(xg_home: float, xg_away: float) -> float:
    """
    Scale fixed ρ toward 0 on extreme matchup styles.

    Dixon–Coles low-score correlation is league-calibrated; applying a global ρ on
    heavy mismatches or very low/high scoring profiles can over-adjust draws.
  """
    lam_h = max(0.1, float(xg_home))
    lam_a = max(0.1, float(xg_away))
    total = lam_h + lam_a
    ratio = max(lam_h, lam_a) / min(lam_h, lam_a)

    # Favourite mismatch (e.g. 2.1 λ vs 0.6 λ)
    if ratio <= 1.8:
        ratio_scale = 1.0
    else:
        ratio_scale = max(0.35, 1.0 - (ratio - 1.8) * 0.35)

    # Defensive slugfest or shootout
    if total < 1.6:
        total_scale = max(0.4, total / 1.6)
    elif total > 3.6:
        total_scale = max(0.45, 1.0 - (total - 3.6) * 0.15)
    else:
        total_scale = 1.0

    return min(ratio_scale, total_scale)


def resolve_dixon_coles_rho(
    league_code: str,
    *,
    xg_home: float,
    xg_away: float,
) -> Tuple[float, Dict[str, Any]]:
    """
    Resolve Dixon–Coles ρ for a single fixture.

    Per-league cache (grid-fit from audit) is used as-is. Fixed env default is
    match-style restricted until per-league MLE is implemented.
    """
    base_rho, base_dbg = league_rho_for_predict(league_code)
    source = str(base_dbg.get("source") or "env_default")
    dbg: Dict[str, Any] = {
        "source": source,
        "base_rho": base_rho,
        "restriction": None,
    }

    restrict = (os.getenv("HIBS_DIXON_COLES_RHO_MATCH_STYLE") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )

    if source == "cache" or not restrict:
        dbg["effective_rho"] = base_rho
        dbg["match_style_scale"] = 1.0
        if not restrict and source != "cache":
            dbg["restriction"] = "match_style_disabled"
        return base_rho, dbg

    scale = _match_style_rho_scale(xg_home, xg_away)
    effective = _clamp_rho(base_rho * scale)
    lam_h = max(0.1, float(xg_home))
    lam_a = max(0.1, float(xg_away))
    dbg.update(
        {
            "effective_rho": effective,
            "match_style_scale": round(scale, 3),
            "lambda_total": round(lam_h + lam_a, 3),
            "lambda_ratio": round(max(lam_h, lam_a) / min(lam_h, lam_a), 3),
            "restriction": "fixed_rho_match_style_until_mle",
        }
    )
    return effective, dbg


def load_league_rho_map() -> Dict[str, float]:
    """Per-league Dixon–Coles ρ from calibration cache."""
    raw = load_calibration_payload()
    leagues = raw.get("leagues") if isinstance(raw, dict) else {}
    if not isinstance(leagues, dict):
        return {}
    out: Dict[str, float] = {}
    for lg, val in leagues.items():
        if not isinstance(val, dict):
            continue
        try:
            if val.get("rho") is not None:
                out[str(lg).upper()] = _clamp_rho(float(val["rho"]))
        except (TypeError, ValueError):
            continue
    return out


def league_rho_for_predict(league_code: str) -> Tuple[float, Dict[str, Any]]:
    """Resolve Dixon–Coles ρ: per-league cache → env default."""
    dbg: Dict[str, Any] = {"source": "env_default"}
    try:
        default = float(os.getenv("HIBS_DIXON_COLES_RHO", "-0.10"))
    except ValueError:
        default = -0.10
    default = _clamp_rho(default)
    code = (league_code or "").upper()
    cached = load_league_rho_map()
    if code in cached:
        dbg = {"source": "cache", "rho": cached[code]}
        return cached[code], dbg
    dbg["rho"] = default
    return default, dbg


def _isotonic_apply(p: float, knots: Dict[str, Any]) -> float:
    xs = knots.get("x") or knots.get("X")
    ys = knots.get("y") or knots.get("Y")
    if not isinstance(xs, list) or not isinstance(ys, list) or len(xs) < 2 or len(xs) != len(ys):
        return p
    try:
        px = max(0.0, min(1.0, float(p)))
        x_vals = [float(x) for x in xs]
        y_vals = [float(y) for y in ys]
        if px <= x_vals[0]:
            return max(1e-6, min(1.0 - 1e-6, y_vals[0]))
        if px >= x_vals[-1]:
            return max(1e-6, min(1.0 - 1e-6, y_vals[-1]))
        for i in range(len(x_vals) - 1):
            if x_vals[i] <= px <= x_vals[i + 1]:
                span = x_vals[i + 1] - x_vals[i]
                if span <= 0:
                    return y_vals[i + 1]
                t = (px - x_vals[i]) / span
                return max(1e-6, min(1.0 - 1e-6, y_vals[i] * (1.0 - t) + y_vals[i + 1] * t))
    except (TypeError, ValueError):
        return p
    return p


def apply_ml_isotonic_calibration(
    probs: Dict[str, float],
    league_code: str = "",
) -> Tuple[Dict[str, float], Dict[str, Any]]:
    """Apply global isotonic knots from calibration cache to ML 1X2 head (if present)."""
    raw = load_calibration_payload()
    ml_cal = raw.get("ml_calibration") if isinstance(raw, dict) else None
    if not isinstance(ml_cal, dict):
        return probs, {"applied": False}
    global_knots = ml_cal.get("global")
    if not isinstance(global_knots, dict):
        return probs, {"applied": False}
    out = dict(probs)
    applied = False
    for k in ("home", "draw", "away"):
        knots = global_knots.get(k)
        if not isinstance(knots, dict):
            continue
        if k not in out:
            continue
        out[k] = _isotonic_apply(float(out[k]), knots)
        applied = True
    if not applied:
        return probs, {"applied": False}
    total = sum(float(out.get(k, 0.0)) for k in ("home", "draw", "away"))
    if total <= 0:
        return probs, {"applied": False}
    out = {k: max(1e-6, float(out[k]) / total) for k in ("home", "draw", "away")}
    return out, {"applied": True, "source": "ml_calibration_global", "league": (league_code or "").upper()}


def load_league_shrink_map() -> Dict[str, float]:
    """Load pre-fit league shrink factors from cache JSON."""
    raw = load_calibration_payload()
    if not raw:
        return {}
    leagues = raw.get("leagues") if isinstance(raw, dict) else raw
    if not isinstance(leagues, dict):
        return {}
    out: Dict[str, float] = {}
    for lg, val in leagues.items():
        try:
            if isinstance(val, dict):
                out[str(lg).upper()] = _clamp_shrink(float(val.get("shrink") or val.get("calibration_shrink") or 1.0))
            else:
                out[str(lg).upper()] = _clamp_shrink(float(val))
        except (TypeError, ValueError):
            continue
    return out


def league_shrink_for_predict(league_code: str) -> Tuple[float, Dict[str, Any]]:
    """
    Resolve calibration_shrink for a league: cache file, else live audit Brier when enabled.
    """
    dbg: Dict[str, Any] = {"source": "default", "shrink": 1.0}
    cached = load_league_shrink_map()
    code = (league_code or "").upper()
    if code in cached:
        dbg["source"] = "cache"
        shrink = cached[code]
        if code == "CHAMPIONSHIP":
            shrink = _championship_calibration_shrink(shrink)
        dbg["shrink"] = shrink
        return shrink, dbg

    from hibs_predictor.prediction_log import brier_by_league, prediction_log_enabled

    if not prediction_log_enabled():
        return 1.0, dbg

    rows = brier_by_league()
    min_n = _env_int("HIBS_CALIB_MIN_LEAGUE_ROWS", 25)
    baseline = _env_float("HIBS_CALIB_BASELINE_BRIER", 0.66)
    league_row = next((r for r in rows if str(r.get("league", "")).upper() == code), None)
    if not league_row or int(league_row.get("n") or 0) < min_n:
        global_rows = [r for r in rows if int(r.get("n") or 0) >= min_n]
        if global_rows:
            baseline = sum(float(r["brier"]) * int(r["n"]) for r in global_rows) / sum(int(r["n"]) for r in global_rows)
        return 1.0, {**dbg, "baseline_brier": round(baseline, 4), "min_rows": min_n}

    lb = float(league_row["brier"])
    shrink = shrink_multiplier_from_brier(lb, baseline, league_code=code)
    dbg = {
        "source": "audit_brier",
        "shrink": round(shrink, 4),
        "league_brier": round(lb, 5),
        "baseline_brier": round(baseline, 5),
        "n_rows": int(league_row["n"]),
    }
    return shrink, dbg


def venue_form_sample_counts(fixture: Dict[str, Any]) -> Tuple[int, int]:
    """Home-side home games and away-side away games in parsed last-10 rows."""
    nh = sum(
        1
        for r in fixture.get("home_last10") or []
        if str(r.get("home_away") or "").upper() == "H"
    )
    na = sum(
        1
        for r in fixture.get("away_last10") or []
        if str(r.get("home_away") or "").upper() == "A"
    )
    return nh, na


def _bet_conf_use_venue_form() -> bool:
    return os.getenv("HIBS_BET_CONF_VENUE_FORM", "1").lower() not in ("0", "false", "no", "off")


def compute_bet_confidence(
    dq_pct: float,
    n_home: int,
    n_away: int,
    xg_source: Any,
    *,
    n_home_venue: Optional[int] = None,
    n_away_venue: Optional[int] = None,
) -> float:
    """0–100 score combining data quality, form depth, and xG tier."""
    dq = max(0.0, min(100.0, float(dq_pct or 0)))
    overall_n = min(int(n_home or 0), int(n_away or 0))
    if _bet_conf_use_venue_form() and (n_home_venue is not None or n_away_venue is not None):
        venue_n = min(int(n_home_venue or 0), int(n_away_venue or 0))
        form_n = min(overall_n, venue_n) if overall_n > 0 else venue_n
    else:
        form_n = overall_n
    form_pts = min(30.0, form_n * 3.0)
    tier = xg_quality_tier(xg_source)
    xg_pts = {"high": 35.0, "medium": 22.0, "low": 10.0}.get(tier, 15.0)
    raw = dq * 0.35 + form_pts + xg_pts
    return round(max(0.0, min(100.0, raw)), 1)


def min_bet_confidence_for_value() -> float:
    return _env_float("HIBS_VALUE_MIN_BET_CONFIDENCE", 42.0)


def confidence_display_scale(confidence: float, n_home: int, n_away: int) -> float:
    """Reduce displayed confidence when form sample is thin."""
    n = min(int(n_home or 0), int(n_away or 0))
    if n >= 5:
        return confidence
    return confidence * max(0.55, n / 5.0)
