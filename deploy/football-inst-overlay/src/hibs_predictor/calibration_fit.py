"""
Fit league calibration (shrink, Dixon–Coles ρ, ML isotonic) from prediction audit rows.

Usage:
  HIBS_PREDICTION_LOG_ENABLED=1 python -m hibs_predictor.calibration_fit
  # writes .cache/calibration_v1.json (override with HIBS_CALIBRATION_CACHE)
"""

from __future__ import annotations

import json
import os
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv

from hibs_predictor.historic_calibration import (
    _clamp_rho,
    calibration_cache_path,
    load_calibration_payload,
    shrink_multiplier_from_brier,
)
from hibs_predictor.prediction_log import _db_path, brier_by_league, init_db, prediction_log_enabled


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _brier_1x2(probs: Dict[str, float], outcome: str) -> float:
    return sum((float(probs.get(k, 0.0)) - (1.0 if k == outcome else 0.0)) ** 2 for k in ("home", "draw", "away"))


def _poisson_1x2_with_rho(xg_h: float, xg_a: float, rho: float) -> Dict[str, float]:
    from hibs_predictor.betting_engine import BettingEngine

    engine = BettingEngine({})
    lam_h = max(0.1, float(xg_h))
    lam_a = max(0.1, float(xg_a))
    max_goals = 8
    home_win = draw = away_win = 0.0
    for h in range(max_goals + 1):
        for a in range(max_goals + 1):
            p = (
                engine._poisson_prob(lam_h, h)
                * engine._poisson_prob(lam_a, a)
                * BettingEngine._dixon_coles_tau(h, a, lam_h, lam_a, rho)
            )
            if p <= 0:
                continue
            if h > a:
                home_win += p
            elif h == a:
                draw += p
            else:
                away_win += p
    total = home_win + draw + away_win
    if total <= 0:
        return {"home": 1.0 / 3.0, "draw": 1.0 / 3.0, "away": 1.0 / 3.0}
    return {
        "home": home_win / total,
        "draw": draw / total,
        "away": away_win / total,
    }


def _scored_audit_rows(
    *,
    trial_leagues_only: bool = False,
    leagues_only: Optional[set] = None,
    kickoff_since: Optional[str] = None,
) -> List[Dict[str, Any]]:
    path = _db_path()
    if not os.path.isfile(path):
        return []
    init_db()
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        clauses = [
            "result_outcome IS NOT NULL",
            "result_outcome IN ('home', 'draw', 'away')",
        ]
        params: List[Any] = []
        if kickoff_since:
            clauses.append("kickoff_iso >= ?")
            params.append(kickoff_since)
        if leagues_only:
            placeholders = ",".join("?" * len(leagues_only))
            clauses.append(f"league_code IN ({placeholders})")
            params.extend(sorted(leagues_only))
        elif trial_leagues_only:
            from hibs_predictor.institutional_readiness import _TRIAL_VALUE_LEAGUES

            trial = sorted(_TRIAL_VALUE_LEAGUES - {"WORLD_CUP", "INTL_FRIENDLIES"})
            if trial:
                placeholders = ",".join("?" * len(trial))
                clauses.append(f"league_code IN ({placeholders})")
                params.extend(trial)
        where = " AND ".join(clauses)
        cur = conn.execute(
            f"""
            SELECT league_code, result_outcome, prediction_json,
                   enrich_summary_json, kickoff_iso
            FROM prediction_snapshots
            WHERE {where}
            ORDER BY id DESC
            LIMIT 8000
            """,
            tuple(params),
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def _scored_audit_rows_filtered(
    *,
    trial_leagues_only: bool = False,
    leagues_only: Optional[set] = None,
    kickoff_since: Optional[str] = None,
) -> List[Dict[str, Any]]:
    return _scored_audit_rows(
        trial_leagues_only=trial_leagues_only,
        leagues_only=leagues_only,
        kickoff_since=kickoff_since,
    )


def _row_clv_pp(row: Dict[str, Any]) -> Optional[float]:
    from hibs_predictor.prediction_log import _clv_pp_from_enrich

    return _clv_pp_from_enrich(row.get("enrich_summary_json"))


def fit_ml_isotonic_from_rows(
    rows: List[Dict[str, Any]],
    *,
    min_rows: int = 40,
    clv_weighted: bool = False,
) -> Optional[Dict[str, Any]]:
    """Fit isotonic calibrators for ML 1X2 head from explicit audit rows."""
    xs: Dict[str, List[float]] = {"home": [], "draw": [], "away": []}
    ys: Dict[str, List[int]] = {"home": [], "draw": [], "away": []}
    weights: Dict[str, List[float]] = {"home": [], "draw": [], "away": []}
    for row in rows:
        outcome = str(row.get("result_outcome") or "")
        if outcome not in xs:
            continue
        try:
            pred = json.loads(row.get("prediction_json") or "{}")
        except json.JSONDecodeError:
            continue
        ml_pct = pred.get("ml_probs_pct") or {}
        if not isinstance(ml_pct, dict):
            continue
        clv_pp = _row_clv_pp(row) if clv_weighted else None
        w_base = 1.0
        if clv_weighted and clv_pp is not None:
            w_base = max(0.25, min(3.0, 1.0 + float(clv_pp) / 8.0))
        for k in ("home", "draw", "away"):
            try:
                p = float(ml_pct.get(k)) / 100.0
            except (TypeError, ValueError):
                continue
            if p <= 0 or p >= 1:
                continue
            xs[k].append(p)
            ys[k].append(1 if outcome == k else 0)
            weights[k].append(w_base)

    if sum(len(v) for v in xs.values()) < min_rows:
        return None

    try:
        from sklearn.isotonic import IsotonicRegression
    except ImportError:
        return None

    global_knots: Dict[str, Dict[str, List[float]]] = {}
    for k in ("home", "draw", "away"):
        if len(xs[k]) < max(12, min_rows // 3):
            continue
        reg = IsotonicRegression(out_of_bounds="clip", y_min=1e-6, y_max=1.0 - 1e-6)
        if clv_weighted and weights[k]:
            reg.fit(xs[k], ys[k], sample_weight=weights[k])
        else:
            reg.fit(xs[k], ys[k])
        x_arr = sorted(set(xs[k]))
        if len(x_arr) < 2:
            continue
        y_arr = [float(reg.predict([x])[0]) for x in x_arr]
        global_knots[k] = {"x": [round(v, 4) for v in x_arr], "y": [round(v, 4) for v in y_arr]}

    if not global_knots:
        return None
    return {
        "method": "isotonic",
        "global": global_knots,
        "n_rows": sum(len(xs[k]) for k in xs),
        "clv_weighted": bool(clv_weighted),
        "fitted_at": datetime.now(timezone.utc).isoformat(),
    }


def fit_ml_isotonic_global(*, min_rows: int = 40) -> Optional[Dict[str, Any]]:
    """Fit isotonic calibrators for ML 1X2 head (home/draw/away) from audit snapshots."""
    load_dotenv()
    trial_only = (os.getenv("HIBS_CALIB_TRIAL_LEAGUES_ONLY") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    clv_weighted = (os.getenv("HIBS_CALIB_CLV_WEIGHT") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    rows = _scored_audit_rows(trial_leagues_only=trial_only)
    return fit_ml_isotonic_from_rows(rows, min_rows=min_rows, clv_weighted=clv_weighted)


def fit_league_dixon_coles_rho(*, min_rows: int = 15) -> Dict[str, Dict[str, Any]]:
    """Grid-search ρ per league on scored rows (minimise Poisson+DC Brier)."""
    rows = _scored_audit_rows()
    by_league: Dict[str, List[Tuple[float, float, str]]] = defaultdict(list)
    for row in rows:
        league = str(row.get("league_code") or "").upper()
        outcome = str(row.get("result_outcome") or "")
        if not league or outcome not in ("home", "draw", "away"):
            continue
        try:
            pred = json.loads(row.get("prediction_json") or "{}")
        except json.JSONDecodeError:
            continue
        xg_h = float(pred.get("expected_goals_home") or 0)
        xg_a = float(pred.get("expected_goals_away") or 0)
        if xg_h <= 0 or xg_a <= 0:
            continue
        by_league[league].append((xg_h, xg_a, outcome))

    grid = [round(x, 3) for x in [i / 100.0 for i in range(-20, 6)]]
    out: Dict[str, Dict[str, Any]] = {}
    for league, samples in by_league.items():
        if len(samples) < min_rows:
            continue
        best_rho = _env_float("HIBS_DIXON_COLES_RHO", -0.10)
        best_brier = 1.0
        for rho in grid:
            total = 0.0
            for xg_h, xg_a, outcome in samples:
                probs = _poisson_1x2_with_rho(xg_h, xg_a, rho)
                total += _brier_1x2(probs, outcome)
            mean_b = total / len(samples)
            if mean_b < best_brier:
                best_brier = mean_b
                best_rho = rho
        out[league] = {
            "rho": round(_clamp_rho(best_rho), 4),
            "brier_rho_fit": round(best_brier, 5),
            "n": len(samples),
        }
    return out


def fit_league_shrink_factors(
    *,
    days: int = 90,
    min_rows: int = 20,
) -> dict:
    """Export league shrink map from audit Brier (rows in window are all scored rows for now)."""
    load_dotenv()
    if not os.path.isfile(_db_path()):
        return {"ok": False, "error": "no_database", "path": _db_path()}
    init_db()
    rows = brier_by_league()
    min_n = _env_int("HIBS_CALIB_FIT_MIN_ROWS", min_rows)
    baseline = _env_float("HIBS_CALIB_BASELINE_BRIER", 0.66)
    eligible = [r for r in rows if int(r.get("n") or 0) >= min_n and r.get("brier") is not None]
    if eligible:
        baseline = sum(float(r["brier"]) * int(r["n"]) for r in eligible) / sum(int(r["n"]) for r in eligible)

    existing = load_calibration_payload()
    leagues: Dict[str, Any] = dict(existing.get("leagues") or {}) if isinstance(existing.get("leagues"), dict) else {}

    for r in rows:
        n = int(r.get("n") or 0)
        if n < min_n or r.get("brier") is None:
            continue
        lg = str(r["league"]).upper()
        lb = float(r["brier"])
        shrink = shrink_multiplier_from_brier(lb, baseline, league_code=lg)
        entry = dict(leagues.get(lg) or {})
        entry.update({"shrink": round(shrink, 4), "brier": round(lb, 5), "n": n})
        leagues[lg] = entry

    rho_map = fit_league_dixon_coles_rho(min_rows=max(10, min_n // 2))
    for lg, rho_entry in rho_map.items():
        entry = dict(leagues.get(lg) or {})
        entry.update(rho_entry)
        leagues[lg] = entry

    ml_cal = fit_ml_isotonic_global(min_rows=max(min_n, 40))

    payload: Dict[str, Any] = {
        "ok": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window_days": days,
        "baseline_brier": round(baseline, 5),
        "min_rows": min_n,
        "trial_leagues_only": (os.getenv("HIBS_CALIB_TRIAL_LEAGUES_ONLY") or "").strip().lower()
        in ("1", "true", "yes", "on"),
        "clv_weighted": (os.getenv("HIBS_CALIB_CLV_WEIGHT") or "").strip().lower()
        in ("1", "true", "yes", "on"),
        "leagues": leagues,
    }
    if ml_cal:
        payload["ml_calibration"] = ml_cal
    elif isinstance(existing.get("ml_calibration"), dict):
        payload["ml_calibration"] = existing["ml_calibration"]
    return payload


def write_calibration_cache(payload: dict) -> str:
    path = calibration_cache_path()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    return path


def main() -> None:
    load_dotenv()
    if not prediction_log_enabled() and not os.path.isfile(_db_path()):
        print("Enable HIBS_PREDICTION_LOG_ENABLED=1 and accumulate snapshots before fitting.")
        return
    days = _env_int("HIBS_CALIB_FIT_DAYS", 90)
    payload = fit_league_shrink_factors(days=days)
    if not payload.get("ok"):
        print(json.dumps(payload, indent=2))
        return
    path = write_calibration_cache(payload)
    n_rho = sum(1 for v in (payload.get("leagues") or {}).values() if isinstance(v, dict) and v.get("rho") is not None)
    ml = payload.get("ml_calibration")
    print(
        f"Wrote {len(payload.get('leagues') or {})} league entries ({n_rho} with ρ) to {path}"
        + (f"; ML isotonic on {ml.get('n_rows')} rows" if isinstance(ml, dict) else "")
    )


if __name__ == "__main__":
    main()
