"""Refined betting engine with Poisson model, fixed Kelly Criterion, and clear value bet output."""

import json
import math
import os
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime

import numpy as np

from hibs_predictor.calibrated_lambdas import calibrated_match_lambdas
from hibs_predictor.historic_calibration import (
    adjust_xg_for_source_quality,
    apply_calibration_shrink,
    apply_form_weight_to_features,
    apply_ml_isotonic_calibration,
    blend_h2h_into_1x2,
    compute_bet_confidence,
    venue_form_sample_counts,
    confidence_display_scale,
    extract_h2h_from_recent,
    form_sample_weight,
    league_rho_for_predict,
    resolve_dixon_coles_rho,
    league_shrink_for_predict,
    min_bet_confidence_for_value,
)
from hibs_predictor.league_profiles import (
    apply_league_probability_profile,
    get_league_profile,
    laplace_1x2_model_weight,
    predict_min_data_quality_pct,
    value_margin_extra,
)
from hibs_predictor.odds_devig import blend_probs_toward_anchor
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler


def _allow_dummy_numeric() -> bool:
    return (os.getenv("HIBS_ALLOW_DUMMY") or "").strip().lower() in ("1", "true", "yes", "on")


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _value_markets_enabled() -> set:
    raw = (os.getenv("HIBS_VALUE_MARKETS") or "1x2,btts,ou").strip().lower()
    tokens = {t.strip() for t in raw.split(",") if t.strip()}
    if not tokens:
        tokens = {"1x2", "btts", "ou"}
    return tokens


def _value_league_allowed(league_code: str) -> bool:
    raw = (os.getenv("HIBS_VALUE_LEAGUES") or "").strip()
    if not raw:
        return True
    allowed = {x.strip().upper() for x in raw.split(",") if x.strip()}
    return str(league_code or "").strip().upper() in allowed


def _is_cup_or_playoff_fixture(fixture: Dict[str, Any]) -> bool:
    meta = fixture.get("competition_meta") or {}
    if not isinstance(meta, dict):
        return False
    rnd = str(meta.get("api_round") or "").lower()
    if not rnd:
        return False
    markers = (
        "final",
        "semi",
        "quarter",
        "round of",
        "play-off",
        "playoff",
        "knockout",
        "cup",
    )
    return any(m in rnd for m in markers)


def _real_xg_source(xg_source: Any) -> bool:
    s = str(xg_source or "").lower()
    return s in ("understat_xg", "api_xg", "stats_api_xg") or "api" in s and "xg" in s


def _best_1x2_odds_from_fixture(fixture: Dict[str, Any]) -> Dict[str, float]:
    """Line-shopped best prices for 1X2 (falls back to fixture triplet)."""
    best = fixture.get("best_odds_1x2") or {}
    out: Dict[str, float] = {}
    for side in ("home", "draw", "away"):
        raw = best.get(side)
        if raw is None:
            raw = fixture.get(f"odds_{side}")
        try:
            fv = float(raw) if raw is not None else 0.0
        except (TypeError, ValueError):
            continue
        if fv > 1.0:
            out[side] = fv
    return out


def _odds_cross_reject_pct() -> float:
    return _env_float("HIBS_ODDS_CROSS_REJECT_PCT", 10.0)


def _friendlies_value_margin_extra(league_code: str) -> float:
    if str(league_code or "").strip().upper() != "INTL_FRIENDLIES":
        return 0.0
    return _env_float("HIBS_FRIENDLIES_VALUE_MARGIN_EXTRA", 0.025)


def _gate_league_margin_delta(league_code: str) -> float:
    """Optional offline-research margin bump (HIBS_GATE_LEAGUE_MARGIN_DELTA_JSON)."""
    raw = (os.getenv("HIBS_GATE_LEAGUE_MARGIN_DELTA_JSON") or "").strip()
    if not raw:
        return 0.0
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            return 0.0
        return float(data.get(str(league_code or "").upper(), 0.0) or 0.0)
    except (TypeError, ValueError, json.JSONDecodeError):
        return 0.0


def _friendlies_value_dq_floor(league_code: str) -> float:
    if str(league_code or "").strip().upper() != "INTL_FRIENDLIES":
        return 0.0
    return _env_float("HIBS_FRIENDLIES_VALUE_DQ_PCT", 88.0)


def _friendlies_market_blend_extra(league_code: str) -> float:
    if str(league_code or "").strip().upper() != "INTL_FRIENDLIES":
        return 0.0
    return _env_float("HIBS_FRIENDLIES_MARKET_BLEND_EXTRA", 0.04)


def _value_max_odds() -> float:
    return _env_float("HIBS_VALUE_MAX_ODDS", 6.0)


def _value_consensus_margin() -> float:
    return _env_float("HIBS_VALUE_CONSENSUS_MARGIN", 0.03)


def _value_consensus_min_model() -> float:
    return _env_float("HIBS_VALUE_CONSENSUS_MIN_MODEL", 0.52)


def _sharpen_gates_enabled() -> bool:
    return (os.getenv("HIBS_SHARPEN_GATES") or "").strip().lower() in ("1", "true", "yes", "on")


def _away_tighten_enabled() -> bool:
    """Optional micro-gate for away / away+BTTS value legs (stacks with sharpen; default off)."""
    return (os.getenv("HIBS_AWAY_TIGHTEN") or "").strip().lower() in ("1", "true", "yes", "on")


def _under_tighten_enabled() -> bool:
    """Optional micro-gate for under 1.5/2.5/3.5 value legs (stacks with sharpen; default off)."""
    return (os.getenv("HIBS_UNDER_TIGHTEN") or "").strip().lower() in ("1", "true", "yes", "on")


def _is_away_value_outcome(outcome: str) -> bool:
    return outcome in ("away", "away_and_btts")


def _is_under_value_outcome(outcome: str) -> bool:
    return outcome in ("under15", "under25", "under35")


def _minutes_to_kickoff(fixture: Dict[str, Any]) -> Optional[float]:
    ko = _fixture_kickoff_dt(fixture)
    if ko is None:
        return None
    now = datetime.now(ko.tzinfo)
    return (ko - now).total_seconds() / 60.0


def _value_odds_class(outcome: str, odds: float, book_1x2: Dict[str, float]) -> str:
    """Classify a value pick as favorite, neutral, or outsider for UI filtering."""
    if odds <= 1.0:
        return "neutral"
    if outcome in ("home", "draw", "away"):
        prices = []
        for side in ("home", "draw", "away"):
            raw = book_1x2.get(side)
            try:
                fv = float(raw) if raw is not None else 0.0
            except (TypeError, ValueError):
                continue
            if fv > 1.0:
                prices.append(fv)
        if prices:
            fav_odds = min(prices)
            if odds <= fav_odds * 1.12:
                return "favorite"
            if odds >= max(4.0, fav_odds * 1.85):
                return "outsider"
            return "neutral"
    if odds <= 1.85:
        return "favorite"
    if odds >= 4.5:
        return "outsider"
    return "neutral"


def _fixture_team_display_name(fixture: Dict[str, Any], side: str) -> str:
    blk = fixture.get(side)
    if isinstance(blk, dict):
        return str(blk.get("name") or "?")
    return str(blk or "?")


def _line_odds_from_fixture_markets(fixture: Dict[str, Any]) -> Dict[str, Any]:
    """Same keys as full predictions; only include sides present on the fixture (book prices, no model)."""
    mo = fixture.get("market_odds") or {}
    line_odds: Dict[str, Any] = {}

    def _take(key: str, raw: Any) -> None:
        if raw is None:
            return
        try:
            fv = float(raw)
        except (TypeError, ValueError):
            return
        if fv > 1.0:
            line_odds[key] = round(fv, 2)

    bt = mo.get("btts") or {}
    _take("btts_yes", bt.get("yes"))
    _take("btts_no", bt.get("no"))
    t15 = mo.get("totals_1_5") or {}
    _take("over15", t15.get("over"))
    _take("under15", t15.get("under"))
    t25 = mo.get("totals_2_5") or {}
    _take("over25", t25.get("over"))
    _take("under25", t25.get("under"))
    t35 = mo.get("totals_3_5") or {}
    _take("over35", t35.get("over"))
    _take("under35", t35.get("under"))
    return line_odds


def _prediction_unavailable_pq_summary(reason: str, has_book_triplet: bool, has_side_lines: bool) -> str:
    if reason == "model_error":
        return "Model step failed; prices shown (if any) are from book feeds only, not the model."
    if reason == "fixture_enrichment_failed":
        if has_book_triplet and has_side_lines:
            return "Enrichment incomplete; 1X2 and side prices from book feeds only."
        if has_book_triplet:
            return "Enrichment incomplete; 1X2 prices from book feeds only."
        if has_side_lines:
            return "Enrichment incomplete; side-market prices from book feeds only."
        return "Enrichment failed; prices shown (if any) are from book feeds only, not the model."
    return "Prediction unavailable; prices shown (if any) are from book feeds only, not the model."


def laplace_smooth_1x2(
    probs: Dict[str, float],
    *,
    model_weight: float = 0.85,
    uniform: float = 1.0 / 3.0,
) -> Dict[str, float]:
    """Pull 1X2 probabilities toward uniform — reduces Brier penalty on upsets."""
    if model_weight >= 1.0:
        return dict(probs)
    w = max(0.0, min(1.0, model_weight))
    out = {k: float(probs.get(k, uniform)) * w + uniform * (1.0 - w) for k in ("home", "draw", "away")}
    total = sum(out.values())
    if total <= 0:
        return dict(probs)
    return {k: v / total for k, v in out.items()}


def prediction_unavailable_payload(fixture: Dict[str, Any], reason: str) -> Dict[str, Any]:
    """Explicit no-prediction shape for the dashboard (no fabricated probabilities or xG)."""
    home = _fixture_team_display_name(fixture, "home")
    away = _fixture_team_display_name(fixture, "away")
    dq_bundle = fixture.get("data_quality") or {}
    oh_raw, od_raw, oa_raw = fixture.get("odds_home"), fixture.get("odds_draw"), fixture.get("odds_away")
    try:
        book_h = float(oh_raw) if oh_raw is not None and float(oh_raw) > 1.0 else None
        book_d = float(od_raw) if od_raw is not None and float(od_raw) > 1.0 else None
        book_a = float(oa_raw) if oa_raw is not None and float(oa_raw) > 1.0 else None
    except (TypeError, ValueError):
        book_h = book_d = book_a = None
    bookmaker_odds = {"home": book_h, "draw": book_d, "away": book_a}
    has_book_triplet = book_h is not None and book_d is not None and book_a is not None
    line_odds = _line_odds_from_fixture_markets(fixture)
    has_side_lines = bool(line_odds)
    pq_summary = _prediction_unavailable_pq_summary(reason, has_book_triplet, has_side_lines)
    try:
        cross_implied = float(fixture.get("odds_cross_max_implied_diff_pct") or 0.0)
    except (TypeError, ValueError):
        cross_implied = 0.0
    out: Dict[str, Any] = {
        "prediction_unavailable": True,
        "prediction_unavailable_reason": reason,
        "fixture": f"{home} vs {away}",
        "home": home,
        "away": away,
        "probabilities": None,
        "probabilities_pct": None,
        "predicted_outcome": None,
        "confidence": None,
        "confidence_pct": None,
        "bookmaker_odds": bookmaker_odds,
        "odds_source_bookmaker": has_book_triplet,
        "value_bets": {},
        "value_bets_display": [],
        "value_highlights": [],
        "line_odds": line_odds,
        "has_any_value": False,
        "best_bet": None,
        "best_bet_roi": None,
        "data_quality": dq_bundle if dq_bundle else None,
        "xg_source": fixture.get("xg_source"),
        "value_bets_gated_by_data": False,
        "value_edge_margin_used": None,
        "score_and_btts_pct": None,
        "odds_cross_max_implied_diff_pct": cross_implied,
        "expected_goals_home": None,
        "expected_goals_away": None,
        "btts_probability": None,
        "btts_probability_pct": None,
        "over15_probability_pct": None,
        "over25_probability_pct": None,
        "over35_probability_pct": None,
        "team_strength_home": None,
        "team_strength_away": None,
        "form_home": None,
        "form_away": None,
        "poisson_probs": None,
        "one_x2_mode": "unavailable",
        "supplemental_xg_prior": None,
        "prediction_quality_hint": {
            "data_score_pct": (dq_bundle or {}).get("score_pct"),
            "full_scope": (dq_bundle or {}).get("full_scope"),
            "supplemental_errors": [],
            "heavy_scrape": "not_run",
            "summary": pq_summary,
        },
        "lambda_side_home": None,
        "lambda_side_away": None,
        "lambda_calibration": {},
        "blend_weights_1x2": None,
        "poisson_probs_calibrated_pct": None,
    }
    try:
        from hibs_predictor.match_insight import attach_structured_insight

        attach_structured_insight(fixture, out)
    except Exception:
        pass
    return out


class TeamStrengthCalculator:

    @staticmethod
    def _team_xg_from_fixture_statistics(match: Dict[str, Any], team_id: int) -> Optional[float]:
        """Per-team xG from API-Football finished fixture when statistics[] is present."""
        if not team_id:
            return None
        stats_list = match.get("statistics")
        if not isinstance(stats_list, list):
            return None
        for block in stats_list:
            team = block.get("team") or {}
            if team.get("id") != team_id:
                continue
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
        return None

    @staticmethod
    def calculate_attack_strength(stats: Dict[str, Any]) -> float:
        try:
            goals_for = float(stats.get("goals_for", 0) or 0)
            expected_goals = float(stats.get("expected_goals", goals_for * 0.8) or (goals_for * 0.8))
            attack_power = min(1.0, (goals_for / 50.0) * 0.7 + (expected_goals / 50.0) * 0.3)
            return max(0.0, min(1.0, attack_power))
        except Exception:
            return 0.5

    @staticmethod
    def calculate_defence_strength(stats: Dict[str, Any]) -> float:
        try:
            goals_against = float(stats.get("goals_against", 50) or 50)
            expected_goals_against = float(stats.get("expected_goals_against", goals_against * 0.8) or (goals_against * 0.8))
            defence_power = max(0.0, 1.0 - (goals_against / 50.0))
            xg_defence = max(0.0, 1.0 - (expected_goals_against / 50.0))
            return max(0.0, min(1.0, defence_power * 0.6 + xg_defence * 0.4))
        except Exception:
            return 0.5

    @staticmethod
    def calculate_form_strength(
        recent_results: List[Dict[str, Any]],
        team_id: Optional[int] = None,
        *,
        team_name: str = "",
    ) -> float:
        if not recent_results:
            return 0.5
        from hibs_predictor.data_aggregator import _match_goals_for_team

        points = 0
        xg_diff = 0.0
        used = 0
        for match in recent_results[:10]:
            scored = _match_goals_for_team(match, team_id, team_name=team_name)
            if not scored:
                continue
            gf, ga = scored
            teams = match.get("teams", {}) or {}
            from hibs_predictor.fixture_utils import coerce_team_id

            hid = coerce_team_id((teams.get("home") or {}).get("id"))
            tid = coerce_team_id(team_id)
            if gf > ga:
                points += 3
            elif gf == ga:
                points += 1
            xgf = TeamStrengthCalculator._team_xg_from_fixture_statistics(match, tid or hid or 0)
            if xgf is not None:
                xg_diff += float(xgf) - max(0.04, (gf + ga) / 10.0)
            used += 1
        if used == 0:
            return 0.5
        form_score = points / (used * 3.0)
        xg_bonus = max(-0.1, min(0.1, xg_diff / max(1.0, used * 2.0)))
        return max(0.0, min(1.0, form_score + xg_bonus))

    @staticmethod
    def calculate_home_away_factor(
        team_id: int,
        matches: List[Dict[str, Any]],
        is_home: bool,
        *,
        team_name: str = "",
    ) -> float:
        from hibs_predictor.fixture_utils import coerce_team_id
        from hibs_predictor.live_scores import _team_names_match

        tid = coerce_team_id(team_id)

        def _relevant(m: Dict[str, Any]) -> bool:
            teams = m.get("teams", {}) or {}
            th = teams.get("home") or {}
            ta = teams.get("away") or {}
            hid = coerce_team_id(th.get("id"))
            aid = coerce_team_id(ta.get("id"))
            if is_home:
                if tid is not None and hid == tid:
                    return True
                return bool(team_name and _team_names_match(team_name, str(th.get("name") or "")))
            if tid is not None and aid == tid:
                return True
            return bool(team_name and _team_names_match(team_name, str(ta.get("name") or "")))

        relevant = [m for m in matches if _relevant(m)]
        if not relevant:
            return 1.0
        points = 0
        for match in relevant[:10]:
            goals = match.get("goals", {})
            home = float(goals.get("home", 0) or 0)
            away = float(goals.get("away", 0) or 0)
            if (is_home and home > away) or (not is_home and away > home):
                points += 3
            elif home == away:
                points += 1
        win_rate = points / (len(relevant[:10]) * 3.0)
        return max(0.5, min(1.5, 1.0 + (win_rate - 0.33)))

    @staticmethod
    def parse_last_10_results(
        matches: List[Dict[str, Any]],
        team_id: Optional[int],
        *,
        team_name: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Parse last 10 matches into readable result rows for the UI."""
        from hibs_predictor.fixture_utils import coerce_team_id

        tid = coerce_team_id(team_id)
        name_key = ""
        if team_name:
            import re
            import unicodedata

            text = unicodedata.normalize("NFKD", str(team_name))
            text = "".join(c for c in text if not unicodedata.combining(c)).lower()
            name_key = re.sub(r"[^a-z0-9]+", " ", text).strip()
        if not tid and not name_key:
            return []
        results = []
        for match in matches[:10]:
            status_short = (match.get("fixture", {}) or {}).get("status", {}) or {}
            if status_short.get("short") and status_short.get("short") != "FT":
                continue
            teams = match.get("teams", {})
            goals = match.get("goals", {}) or {}
            home_id = coerce_team_id((teams.get("home") or {}).get("id"))
            away_id = coerce_team_id((teams.get("away") or {}).get("id"))
            home_name = teams.get("home", {}).get("name", "?")
            away_name = teams.get("away", {}).get("name", "?")
            gh, ga = goals.get("home"), goals.get("away")
            if gh is None or ga is None:
                continue
            home_goals = float(gh)
            away_goals = float(ga)
            matched_side = None
            if tid and home_id == tid:
                matched_side = "home"
            elif tid and away_id == tid:
                matched_side = "away"
            elif name_key:
                import re
                import unicodedata

                def _nk(n: str) -> str:
                    t = unicodedata.normalize("NFKD", str(n))
                    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
                    return re.sub(r"[^a-z0-9]+", " ", t).strip()

                hk, ak = _nk(home_name), _nk(away_name)
                if name_key == hk or name_key in hk or hk in name_key:
                    matched_side = "home"
                elif name_key == ak or name_key in ak or ak in name_key:
                    matched_side = "away"
            if matched_side == "home":
                is_home = True
                gf, ga = home_goals, away_goals
                match_tid = home_id or tid
            elif matched_side == "away":
                is_home = False
                gf, ga = away_goals, home_goals
                match_tid = away_id or tid
            else:
                continue
            opponent = away_name if is_home else home_name
            result = "W" if gf > ga else ("L" if gf < ga else "D")
            fixture_date = match.get("fixture", {}).get("date", "") or ""
            tot = int(gf + ga)
            xgf = TeamStrengthCalculator._team_xg_from_fixture_statistics(match, match_tid)
            results.append({
                "result": result,
                "score": f"{int(gf)}-{int(ga)}",
                "opponent": opponent,
                "home_away": "H" if is_home else "A",
                "date": fixture_date[:10],
                "gf": int(gf),
                "ga": int(ga),
                "btts": bool(gf > 0 and ga > 0),
                "over15": tot > 1,
                "over25": tot > 2,
                "xg_for": round(xgf, 2) if xgf is not None else None,
            })
        return results


class OddsAnalyzer:

    @staticmethod
    def decimal_to_probability(decimal_odds: float) -> float:
        if decimal_odds <= 1.0:
            return 0.0
        return 1.0 / decimal_odds

    @staticmethod
    def kelly_criterion(win_probability: float, decimal_odds: float, fraction: float = 0.25) -> Dict[str, Any]:
        """
        Fractional Kelly Criterion as human-readable betting guidance.
        Returns suggested_percent of bankroll, a confidence label, and plain English explanation.
        """
        if decimal_odds <= 1.0 or win_probability <= 0:
            return {
                "raw_fraction": 0.0,
                "suggested_percent": 0.0,
                "confidence_label": "Skip",
                "example_stake": "\u00a30.00",
                "explanation": "No edge detected \u2014 skip this bet.",
            }
        b = decimal_odds - 1.0
        q = 1.0 - win_probability
        kelly = max(0.0, (win_probability * b - q) / b)
        capped = min(0.10, kelly * fraction)
        suggested_percent = round(capped * 100, 1)
        example_stake = round(100 * capped, 2)
        if suggested_percent >= 5.0:
            label, explanation = "Strong", f"Strong edge. Stake ~{suggested_percent}% of bankroll (e.g. \u00a3{example_stake:.2f} per \u00a3100)."
        elif suggested_percent >= 2.5:
            label, explanation = "Moderate", f"Moderate edge. Stake ~{suggested_percent}% of bankroll (e.g. \u00a3{example_stake:.2f} per \u00a3100)."
        elif suggested_percent > 0:
            label, explanation = "Cautious", f"Small edge. Stake ~{suggested_percent}% of bankroll (e.g. \u00a3{example_stake:.2f} per \u00a3100)."
        else:
            label, explanation = "Skip", "No positive edge \u2014 skip this bet."
        return {
            "raw_fraction": round(kelly, 4),
            "suggested_percent": suggested_percent,
            "confidence_label": label,
            "example_stake": f"\u00a3{example_stake:.2f}",
            "explanation": explanation,
        }

    @staticmethod
    def identify_value_bets(
        model_probabilities: Dict[str, float],
        bookmaker_odds: Dict[str, float],
        margin: float = 0.04,
    ) -> Dict[str, Any]:
        value_bets = {}
        for outcome, model_prob in model_probabilities.items():
            if outcome not in bookmaker_odds:
                continue
            odds = bookmaker_odds.get(outcome)
            if odds is None or odds <= 1.0:
                continue
            implied_prob = OddsAnalyzer.decimal_to_probability(odds)
            edge = model_prob - implied_prob
            if edge > margin:
                roi = (edge / implied_prob) * 100
                value_bets[outcome] = {
                    "model_probability": round(model_prob, 4),
                    "model_probability_pct": round(model_prob * 100, 1),
                    "implied_probability": round(implied_prob, 4),
                    "implied_probability_pct": round(implied_prob * 100, 1),
                    "edge": round(edge, 4),
                    "edge_pct": round(edge * 100, 1),
                    "roi_percent": round(roi, 1),
                    "odds": odds,
                    "kelly": OddsAnalyzer.kelly_criterion(model_prob, odds),
                }
        return value_bets

    @staticmethod
    def identify_market_consensus_value(
        model_probabilities: Dict[str, float],
        sharp_implied: Dict[str, float],
        bookmaker_odds: Dict[str, float],
        margin: float = 0.03,
        min_model_prob: float = 0.52,
    ) -> Dict[str, Any]:
        """Value vs median/Pinnacle de-vig implied — surfaces mispriced favourites, not only longshots."""
        if not sharp_implied or not all(sharp_implied.get(s) for s in ("home", "draw", "away")):
            return {}
        value_bets: Dict[str, Any] = {}
        for outcome in ("home", "draw", "away"):
            model_prob = float(model_probabilities.get(outcome, 0.0))
            if model_prob < min_model_prob:
                continue
            sharp = float(sharp_implied.get(outcome, 0.0))
            odds = bookmaker_odds.get(outcome)
            if odds is None or float(odds) <= 1.0:
                continue
            odds = float(odds)
            edge = model_prob - sharp
            if edge > margin:
                roi = (edge / sharp) * 100 if sharp > 0 else 0.0
                value_bets[outcome] = {
                    "model_probability": round(model_prob, 4),
                    "model_probability_pct": round(model_prob * 100, 1),
                    "implied_probability": round(sharp, 4),
                    "implied_probability_pct": round(sharp * 100, 1),
                    "edge": round(edge, 4),
                    "edge_pct": round(edge * 100, 1),
                    "roi_percent": round(roi, 1),
                    "odds": odds,
                    "kelly": OddsAnalyzer.kelly_criterion(model_prob, odds),
                    "source": "market_consensus",
                }
        return value_bets


class BettingEngine:

    @staticmethod
    def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _safe_int(value: Any, default: Optional[int] = None) -> Optional[int]:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @classmethod
    def _position_number(cls, pos: Any) -> Optional[int]:
        if isinstance(pos, dict):
            return cls._safe_int(pos.get("position"))
        return cls._safe_int(pos)

    @classmethod
    def _matchup_context(
        cls,
        fixture: Dict[str, Any],
        metadata: Dict[str, Any],
        xg_home: float,
        xg_away: float,
    ) -> Dict[str, Any]:
        home_pos = cls._position_number(fixture.get("home_position"))
        away_pos = cls._position_number(fixture.get("away_position"))
        home_form = float(metadata.get("home_form") or fixture.get("home_form") or 0.5)
        away_form = float(metadata.get("away_form") or fixture.get("away_form") or 0.5)
        home_strength = float(metadata.get("home_strength") or 0.5)
        away_strength = float(metadata.get("away_strength") or 0.5)
        return {
            "home_pos": home_pos,
            "away_pos": away_pos,
            "table_gap_home_worse": (
                home_pos - away_pos if home_pos is not None and away_pos is not None else None
            ),
            "form_gap_home_minus_away": home_form - away_form,
            "strength_gap_home_minus_away": home_strength - away_strength,
            "xg_gap_home_minus_away": float(xg_home) - float(xg_away),
        }

    @classmethod
    def _apply_mismatch_calibration(
        cls,
        probs: Dict[str, float],
        context: Dict[str, Any],
    ) -> Tuple[Dict[str, float], Optional[Dict[str, Any]]]:
        """Dampen a 1X2 side when table, form, strength and xG all point the other way."""
        out = dict(probs)
        gap = context.get("table_gap_home_worse")
        if gap is None:
            return out, None

        def _transfer_mass(side: str, factor: float, target: str) -> None:
            removed = out[side] * factor
            out[side] = max(1e-6, out[side] - removed)
            out[target] = out.get(target, 0.0) + removed * 0.68
            out["draw"] = out.get("draw", 0.0) + removed * 0.32

        calibration: Optional[Dict[str, Any]] = None
        home_xg_gap = float(context.get("xg_gap_home_minus_away") or 0.0)
        home_form_gap = float(context.get("form_gap_home_minus_away") or 0.0)
        home_strength_gap = float(context.get("strength_gap_home_minus_away") or 0.0)
        if gap >= 8 and home_xg_gap <= -0.35 and (home_form_gap <= -0.12 or home_strength_gap <= -0.10):
            factor = min(0.36, 0.10 + min(18, gap) * 0.009 + min(1.5, abs(home_xg_gap)) * 0.055)
            _transfer_mass("home", factor, "away")
            calibration = {"side_damped": "home", "factor": round(factor, 3), "table_gap": gap}
        elif gap <= -8 and home_xg_gap >= 0.35 and (home_form_gap >= 0.12 or home_strength_gap >= 0.10):
            factor = min(0.36, 0.10 + min(18, abs(gap)) * 0.009 + min(1.5, abs(home_xg_gap)) * 0.055)
            _transfer_mass("away", factor, "home")
            calibration = {"side_damped": "away", "factor": round(factor, 3), "table_gap": gap}

        total = sum(out.values())
        if total > 0:
            out = {k: max(1e-6, v / total) for k, v in out.items()}
        return out, calibration

    @staticmethod
    def _min_probability_for_value(outcome: str) -> float:
        thresholds = {
            "home": 0.24,
            "away": 0.24,
            "draw": 0.27,
            "btts_yes": 0.53,
            "btts_no": 0.53,
            "over15": 0.68,
            "under15": 0.55,
            "over25": 0.54,
            "under25": 0.54,
            "over35": 0.36,
            "under35": 0.58,
            "home_and_btts": 0.16,
            "draw_and_btts": 0.12,
            "away_and_btts": 0.16,
        }
        return thresholds.get(outcome, 0.30)

    @classmethod
    def _evidence_against_1x2(cls, outcome: str, context: Dict[str, Any]) -> Tuple[int, bool]:
        gap = context.get("table_gap_home_worse")
        xg_gap = float(context.get("xg_gap_home_minus_away") or 0.0)
        form_gap = float(context.get("form_gap_home_minus_away") or 0.0)
        strength_gap = float(context.get("strength_gap_home_minus_away") or 0.0)
        if outcome == "home":
            flags = [
                gap is not None and gap >= 8,
                xg_gap <= -0.35,
                form_gap <= -0.12,
                strength_gap <= -0.10,
            ]
        elif outcome == "away":
            flags = [
                gap is not None and gap <= -8,
                xg_gap >= 0.35,
                form_gap >= 0.12,
                strength_gap >= 0.10,
            ]
        else:
            return 0, False
        count = sum(1 for x in flags if x)
        return count, bool(flags[0] and count >= 2)

    @classmethod
    def _filter_value_bets(
        cls,
        value_bets: Dict[str, Any],
        fixture: Dict[str, Any],
        merged_model: Dict[str, float],
        context: Dict[str, Any],
        margin: float,
        dq_pct: float,
        dq_known: bool,
        *,
        markets_enabled: Optional[set] = None,
        cross_pct: float = 0.0,
        xg_source: Any = None,
        bet_confidence: Optional[float] = None,
    ) -> Tuple[Dict[str, Any], Dict[str, str]]:
        filtered: Dict[str, Any] = {}
        rejected: Dict[str, str] = {}
        if dq_known and dq_pct < 68.0:
            return {}, {k: "data_quality_below_value_floor" for k in value_bets}

        enabled = markets_enabled if markets_enabled is not None else _value_markets_enabled()
        cross_limit = _odds_cross_reject_pct()
        steam = cross_pct >= cross_limit
        real_xg = _real_xg_source(xg_source or fixture.get("xg_source"))
        btts_ou_margin_discount = 0.012 if real_xg else 0.0
        sharpen = _sharpen_gates_enabled()
        away_tighten = _away_tighten_enabled()
        under_tighten = _under_tighten_enabled()
        sharp_min_conf = _env_float("HIBS_SHARPEN_MIN_BET_CONFIDENCE", 50.0)
        sharp_min_edge = _env_float("HIBS_SHARPEN_MIN_EDGE", 0.0)
        sharp_gap_max = _env_float("HIBS_SHARPEN_MAX_MODEL_SHARP_GAP_1X2", 0.09)
        sharp_upset_cutoff = _env_float("HIBS_SHARPEN_UPSET_RISK_CUTOFF", 0.13)
        sharp_upset_bump = _env_float("HIBS_SHARPEN_UPSET_EDGE_BUMP", 0.012)
        sharp_min_kickoff_min = _env_float("HIBS_SHARPEN_MIN_KICKOFF_MIN", -1.0)
        sharp_max_kickoff_min = _env_float("HIBS_SHARPEN_MAX_KICKOFF_MIN", -1.0)
        away_edge_bump = _env_float("HIBS_AWAY_TIGHTEN_EDGE_BUMP", 0.015)
        away_long_odds = _env_float("HIBS_AWAY_TIGHTEN_LONG_ODDS", 3.5)
        away_long_odds_bump = _env_float("HIBS_AWAY_TIGHTEN_LONG_ODDS_BUMP", 0.02)
        away_min_conf = _env_float("HIBS_AWAY_TIGHTEN_MIN_CONF", 52.0)
        away_min_edge = _env_float("HIBS_AWAY_TIGHTEN_MIN_EDGE", 0.0)
        under_edge_bump = _env_float("HIBS_UNDER_TIGHTEN_EDGE_BUMP", 0.018)
        under_short_odds = _env_float("HIBS_UNDER_TIGHTEN_SHORT_ODDS", 1.85)
        under_short_odds_bump = _env_float("HIBS_UNDER_TIGHTEN_SHORT_ODDS_BUMP", 0.015)
        under_min_conf = _env_float("HIBS_UNDER_TIGHTEN_MIN_CONF", 54.0)
        under_min_edge = _env_float("HIBS_UNDER_TIGHTEN_MIN_EDGE", 0.0)
        minutes_to_ko = _minutes_to_kickoff(fixture) if sharpen else None
        league_code = str(fixture.get("league") or "").strip().upper()
        league_upset_risk = float(get_league_profile(league_code).get("upset_risk") or 0.0) if sharpen else 0.0

        for outcome, row in value_bets.items():
            if outcome in ("home", "draw", "away") and "1x2" not in enabled:
                rejected[outcome] = "market_disabled_by_env"
                continue
            if outcome.startswith(("btts_", "home_and_btts", "draw_and_btts", "away_and_btts")):
                if "btts" not in enabled:
                    rejected[outcome] = "market_disabled_by_env"
                    continue
            if outcome.startswith(("over", "under")) and "ou" not in enabled:
                rejected[outcome] = "market_disabled_by_env"
                continue
            if steam:
                rejected[outcome] = "odds_cross_book_disagreement"
                continue
            model_prob = float(merged_model.get(outcome, row.get("model_probability") or 0.0))
            odds = cls._safe_float(row.get("odds"), 0.0) or 0.0
            edge = cls._safe_float(row.get("edge"), 0.0) or 0.0
            min_prob = cls._min_probability_for_value(outcome)
            if model_prob < min_prob:
                rejected[outcome] = "model_probability_below_value_floor"
                continue

            required_edge = max(margin, 0.05 if outcome in ("home", "draw", "away") else margin)
            if outcome.startswith(("btts_", "over", "under")) and btts_ou_margin_discount > 0:
                required_edge = max(0.03, required_edge - btts_ou_margin_discount)
            if model_prob < 0.35:
                required_edge += (0.35 - model_prob) * 0.22
            if odds > 4.5:
                required_edge += min(0.08, (odds - 4.5) * 0.014)
            max_odds_cap = _value_max_odds()
            if odds > 8.0 and model_prob < 0.15:
                rejected[outcome] = "longshot_requires_15pct_model"
                continue
            if odds > max_odds_cap and model_prob < max(0.15, 1.0 / max_odds_cap):
                rejected[outcome] = "odds_above_env_cap_without_model_support"
                continue
            if dq_known and dq_pct < 80.0:
                required_edge += (80.0 - dq_pct) * 0.001
            if sharpen and outcome in ("home", "draw", "away") and league_upset_risk >= sharp_upset_cutoff:
                required_edge += sharp_upset_bump
            if away_tighten and _is_away_value_outcome(outcome):
                required_edge += away_edge_bump
                if odds >= away_long_odds:
                    required_edge += away_long_odds_bump
            if under_tighten and _is_under_value_outcome(outcome):
                required_edge += under_edge_bump
                if odds <= under_short_odds:
                    required_edge += under_short_odds_bump
            if edge < required_edge:
                rejected[outcome] = "edge_below_scaled_threshold"
                continue

            sharp_impl = fixture.get("sharp_anchor_implied") or {}
            if outcome in ("home", "draw", "away") and odds >= 4.0 and isinstance(sharp_impl, dict):
                sharp_p = sharp_impl.get(outcome)
                try:
                    sharp_f = float(sharp_p) if sharp_p is not None else None
                except (TypeError, ValueError):
                    sharp_f = None
                if sharp_f is not None and model_prob > sharp_f + 0.055 and model_prob < 0.30:
                    rejected[outcome] = "favorite_longshot_bias_gate"
                    continue
            if outcome.startswith(("btts_", "over", "under")) and odds >= 3.8:
                try:
                    flb_min = float(os.getenv("HIBS_FLB_BTTS_OU_MIN_ODDS", "3.8"))
                except ValueError:
                    flb_min = 3.8
                if odds >= flb_min and model_prob < 0.42 and edge < margin + 0.03:
                    rejected[outcome] = "favorite_longshot_bias_gate"
                    continue

            if outcome in ("home", "draw", "away"):
                if dq_known and dq_pct < 76.0:
                    rejected[outcome] = "data_quality_below_1x2_value_floor"
                    continue
                if outcome == "draw":
                    if odds > 5.0 or model_prob < 0.30:
                        rejected[outcome] = "draw_longshot_floor"
                        continue
                else:
                    against_count, strong_against = cls._evidence_against_1x2(outcome, context)
                    if odds > 6.5:
                        rejected[outcome] = "1x2_longshot_odds_cap"
                        continue
                    if odds > 4.8 and (dq_known and dq_pct < 88.0):
                        rejected[outcome] = "longshot_requires_strong_data"
                        continue
                    if strong_against:
                        if not (model_prob >= 0.34 and edge >= 0.12 and dq_known and dq_pct >= 88.0 and odds <= 5.5):
                            rejected[outcome] = "table_form_xg_disagree"
                            continue
                    elif against_count >= 2 and model_prob < 0.31:
                        rejected[outcome] = "weak_context_for_underdog_value"
                        continue

            if sharpen:
                if sharp_min_edge > 0 and edge < sharp_min_edge:
                    rejected[outcome] = "sharpen_min_edge_gate"
                    continue
                if bet_confidence is not None and bet_confidence < sharp_min_conf:
                    rejected[outcome] = "sharpen_bet_confidence_gate"
                    continue
                if minutes_to_ko is not None:
                    if sharp_min_kickoff_min >= 0 and minutes_to_ko < sharp_min_kickoff_min:
                        rejected[outcome] = "sharpen_kickoff_window_gate"
                        continue
                    if sharp_max_kickoff_min >= 0 and minutes_to_ko > sharp_max_kickoff_min:
                        rejected[outcome] = "sharpen_kickoff_window_gate"
                        continue
                if outcome in ("home", "draw", "away"):
                    sharp_impl = fixture.get("sharp_anchor_implied") or {}
                    if isinstance(sharp_impl, dict):
                        sharp_p = sharp_impl.get(outcome)
                        try:
                            sharp_f = float(sharp_p) if sharp_p is not None else None
                        except (TypeError, ValueError):
                            sharp_f = None
                        if sharp_f is not None and model_prob > sharp_f + sharp_gap_max and edge < (required_edge + 0.02):
                            rejected[outcome] = "sharpen_sharp_anchor_divergence"
                            continue

            if away_tighten and _is_away_value_outcome(outcome):
                if bet_confidence is not None and bet_confidence < away_min_conf:
                    rejected[outcome] = "away_tighten_confidence_gate"
                    continue
                if away_min_edge > 0 and edge < away_min_edge:
                    rejected[outcome] = "away_tighten_min_edge_gate"
                    continue

            if under_tighten and _is_under_value_outcome(outcome):
                if bet_confidence is not None and bet_confidence < under_min_conf:
                    rejected[outcome] = "under_tighten_confidence_gate"
                    continue
                if under_min_edge > 0 and edge < under_min_edge:
                    rejected[outcome] = "under_tighten_min_edge_gate"
                    continue

            filtered[outcome] = row
        return filtered, rejected

    @staticmethod
    def _blend_1x2_toward_implied(
        probs: Dict[str, float],
        book: Dict[str, float],
        strength: float,
    ) -> Dict[str, float]:
        """Pull 1X2 model mass slightly toward de-vig implied odds (fewer spurious value flags)."""
        if strength <= 0 or not book:
            return probs
        if not all(k in probs for k in ("home", "draw", "away")):
            return probs
        impl: Dict[str, float] = {}
        for k in ("home", "draw", "away"):
            o = book.get(k)
            if o is None or float(o) <= 1.0:
                return probs
            impl[k] = OddsAnalyzer.decimal_to_probability(float(o))
        s = sum(impl.values())
        if s <= 0:
            return probs
        impl = {k: impl[k] / s for k in impl}
        out: Dict[str, float] = {}
        for k in ("home", "draw", "away"):
            e = float(probs[k])
            out[k] = e * (1.0 - strength) + impl[k] * strength
        t = sum(out.values())
        if t <= 0:
            return probs
        return {k: max(1e-6, v / t) for k, v in out.items()}

    def __init__(self, clients: Dict[str, Any]) -> None:
        self.clients = clients
        self.scaler = StandardScaler()
        self.rf_model = RandomForestClassifier(n_estimators=200, max_depth=12, random_state=42)
        self.gb_model = GradientBoostingClassifier(n_estimators=150, max_depth=5, random_state=42)
        self.is_trained = False

    def _poisson_prob(self, lam: float, k: int) -> float:
        try:
            return (math.exp(-lam) * (lam ** k)) / math.factorial(k)
        except Exception:
            return 0.0

    @staticmethod
    def _read_dixon_coles_rho(
        league_code: str = "",
        *,
        xg_home: float = 1.3,
        xg_away: float = 1.1,
    ) -> float:
        """Low-score correlation; per-league cache or match-style-restricted fixed ρ."""
        rho, _dbg = resolve_dixon_coles_rho(league_code, xg_home=xg_home, xg_away=xg_away)
        return rho

    @staticmethod
    def _use_bivariate_side_markets() -> bool:
        return os.getenv("HIBS_BIVARIATE_POISSON", "1").strip().lower() not in ("0", "false", "no", "off")

    @staticmethod
    def _dixon_coles_tau(h: int, a: int, lam_h: float, lam_a: float, rho: float) -> float:
        """Dixon–Coles adjustment for (0,0), (1,1), (0,1), (1,0); 1 elsewhere."""
        if abs(rho) < 1e-9:
            return 1.0
        if h == 0 and a == 0:
            return 1.0 - lam_h * lam_a * rho
        if h == 0 and a == 1:
            return 1.0 + lam_h * rho
        if h == 1 and a == 0:
            return 1.0 + lam_a * rho
        if h == 1 and a == 1:
            return 1.0 - rho
        return 1.0

    def _poisson_match_probs(
        self,
        xg_home: float,
        xg_away: float,
        *,
        league_code: str = "",
    ) -> Dict[str, float]:
        max_goals = 8
        lam_h = max(0.1, float(xg_home))
        lam_a = max(0.1, float(xg_away))
        rho = self._read_dixon_coles_rho(league_code, xg_home=lam_h, xg_away=lam_a)
        home_win = draw = away_win = 0.0
        for h in range(max_goals + 1):
            for a in range(max_goals + 1):
                p = (
                    self._poisson_prob(lam_h, h)
                    * self._poisson_prob(lam_a, a)
                    * self._dixon_coles_tau(h, a, lam_h, lam_a, rho)
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
        if total > 0:
            return {"home": home_win / total, "draw": draw / total, "away": away_win / total}
        return {"home": 1.0 / 3.0, "draw": 1.0 / 3.0, "away": 1.0 / 3.0}

    @staticmethod
    def _fair_decimal_from_prob(p: float) -> float:
        """Decimal odds with no vig from a win probability (for feature fill-in only)."""
        p = max(0.03, min(0.97, float(p)))
        return max(1.02, min(80.0, 1.0 / p))

    @staticmethod
    def _read_1x2_mode() -> str:
        """ensemble: ML+Poisson(raw). calibrated_poisson: HA+Elo-proxy Poisson only. blend_all: weighted mix of three 1X2 heads."""
        m = (os.getenv("HIBS_1X2_MODE") or "ensemble").strip().lower()
        if m in ("calibrated_poisson", "blend_all", "ensemble"):
            return m
        return "ensemble"

    @staticmethod
    def _read_blend_weights() -> Tuple[float, float, float]:
        def _f(name: str, default: float) -> float:
            try:
                return float(os.getenv(name, str(default)))
            except ValueError:
                return default

        w_ml = _f("HIBS_BLEND_W_ML", 1.0 / 3.0)
        w_raw = _f("HIBS_BLEND_W_POISSON_RAW", 1.0 / 3.0)
        w_cal = _f("HIBS_BLEND_W_POISSON_CAL", 1.0 / 3.0)
        s = w_ml + w_raw + w_cal
        if s <= 0:
            return (1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0)
        return (w_ml / s, w_raw / s, w_cal / s)

    @staticmethod
    def _merge_three_1x2(
        p_ml: Dict[str, float],
        p_raw: Dict[str, float],
        p_cal: Dict[str, float],
        w_ml: float,
        w_raw: float,
        w_cal: float,
    ) -> Optional[Dict[str, float]]:
        out: Dict[str, float] = {}
        for k in ("home", "draw", "away"):
            out[k] = (
                float(p_ml.get(k, 0.0)) * w_ml
                + float(p_raw.get(k, 0.0)) * w_raw
                + float(p_cal.get(k, 0.0)) * w_cal
            )
        t = sum(out.values())
        if t > 0:
            return {k: max(1e-9, v / t) for k, v in out.items()}
        if _allow_dummy_numeric():
            return {"home": 1.0 / 3.0, "draw": 1.0 / 3.0, "away": 1.0 / 3.0}
        for src in (p_raw, p_cal, p_ml):
            s = sum(float(src.get(k, 0.0)) for k in ("home", "draw", "away"))
            if s > 0:
                return {k: max(1e-9, float(src.get(k, 0.0)) / s) for k in ("home", "draw", "away")}
        return None

    def _poisson_btts_probability(self, lam_h: float, lam_a: float) -> float:
        """Independent Poisson: both teams score at least once."""
        lam_h = max(0.08, float(lam_h))
        lam_a = max(0.08, float(lam_a))
        p_home_scores = 1.0 - self._poisson_prob(lam_h, 0)
        p_away_scores = 1.0 - self._poisson_prob(lam_a, 0)
        return max(0.02, min(0.98, p_home_scores * p_away_scores))

    def _poisson_over_goals_probability(self, lam_h: float, lam_a: float, line: float) -> float:
        """P(total goals > line) for half-goal lines (e.g. 2.5 → sum P(T<=2) subtracted from 1)."""
        lam_h = max(0.08, float(lam_h))
        lam_a = max(0.08, float(lam_a))
        max_total = int(math.floor(float(line)))
        p_at_most = 0.0
        cap = 12
        for h in range(cap + 1):
            for a in range(cap + 1):
                if h + a <= max_total:
                    p_at_most += self._poisson_prob(lam_h, h) * self._poisson_prob(lam_a, a)
        p_at_most = min(1.0, p_at_most)
        over = 1.0 - p_at_most
        return max(0.02, min(0.98, over))

    def _poisson_joint_home_win_and_btts(self, lam_h: float, lam_a: float) -> float:
        lam_h = max(0.08, float(lam_h))
        lam_a = max(0.08, float(lam_a))
        s = 0.0
        cap = 10
        for h in range(1, cap + 1):
            for a in range(1, cap + 1):
                if h > a:
                    s += self._poisson_prob(lam_h, h) * self._poisson_prob(lam_a, a)
        return max(0.001, min(0.95, s))

    def _poisson_joint_draw_and_btts(self, lam_h: float, lam_a: float) -> float:
        lam_h = max(0.08, float(lam_h))
        lam_a = max(0.08, float(lam_a))
        s = 0.0
        cap = 10
        for g in range(1, cap + 1):
            s += self._poisson_prob(lam_h, g) * self._poisson_prob(lam_a, g)
        return max(0.001, min(0.95, s))

    def _poisson_joint_away_win_and_btts(self, lam_h: float, lam_a: float) -> float:
        lam_h = max(0.08, float(lam_h))
        lam_a = max(0.08, float(lam_a))
        s = 0.0
        cap = 10
        for h in range(1, cap + 1):
            for a in range(1, cap + 1):
                if a > h:
                    s += self._poisson_prob(lam_h, h) * self._poisson_prob(lam_a, a)
        return max(0.001, min(0.95, s))

    def build_advanced_features(self, fixture: Dict[str, Any]) -> Tuple[List[float], Dict[str, Any]]:
        home = fixture.get("home", {})
        away = fixture.get("away", {})
        home_id = home.get("id", 0) if isinstance(home, dict) else 0
        away_id = away.get("id", 0) if isinstance(away, dict) else 0
        home_name = home.get("name", str(home)) if isinstance(home, dict) else str(home)
        away_name = away.get("name", str(away)) if isinstance(away, dict) else str(away)
        home_stats = fixture.get("home_stats", {})
        away_stats = fixture.get("away_stats", {})
        home_attack = TeamStrengthCalculator.calculate_attack_strength(home_stats)
        home_defence = TeamStrengthCalculator.calculate_defence_strength(home_stats)
        away_attack = TeamStrengthCalculator.calculate_attack_strength(away_stats)
        away_defence = TeamStrengthCalculator.calculate_defence_strength(away_stats)
        home_form = float(fixture.get("home_form", 0.5) or 0.5)
        away_form = float(fixture.get("away_form", 0.5) or 0.5)
        home_home_factor = float(fixture.get("home_home_factor", 1.0) or 1.0)
        away_away_factor = float(fixture.get("away_away_factor", 1.0) or 1.0)
        home_strength = max(0.0, min(1.0, home_attack * 0.4 + home_defence * 0.2 + home_form * 0.3 + (home_home_factor - 1.0) * 0.1))
        away_strength = max(0.0, min(1.0, away_attack * 0.4 + away_defence * 0.2 + away_form * 0.3 + (away_away_factor - 1.0) * 0.1))
        league_factor = float(fixture.get("league_factor", 1.0) or 1.0)
        xg_home = float(fixture.get("xg_home", 1.2) or 1.2)
        xg_away = float(fixture.get("xg_away", 1.1) or 1.1)
        poisson_pre = self._poisson_match_probs(xg_home, xg_away)
        raw_oh = fixture.get("odds_home")
        raw_od = fixture.get("odds_draw")
        raw_oa = fixture.get("odds_away")
        try:
            odds_home = float(raw_oh) if raw_oh is not None and float(raw_oh) > 1.0 else self._fair_decimal_from_prob(poisson_pre["home"])
            odds_draw = float(raw_od) if raw_od is not None and float(raw_od) > 1.0 else self._fair_decimal_from_prob(poisson_pre["draw"])
            odds_away = float(raw_oa) if raw_oa is not None and float(raw_oa) > 1.0 else self._fair_decimal_from_prob(poisson_pre["away"])
        except (TypeError, ValueError):
            odds_home = self._fair_decimal_from_prob(poisson_pre["home"])
            odds_draw = self._fair_decimal_from_prob(poisson_pre["draw"])
            odds_away = self._fair_decimal_from_prob(poisson_pre["away"])
        features = [
            home_strength, away_strength, home_attack, home_defence, away_attack, away_defence,
            home_form, away_form, home_home_factor, away_away_factor,
            odds_home, odds_draw, odds_away,
            OddsAnalyzer.decimal_to_probability(odds_home),
            OddsAnalyzer.decimal_to_probability(odds_draw),
            OddsAnalyzer.decimal_to_probability(odds_away),
            xg_home, xg_away, xg_home - xg_away,
            home_strength - away_strength, home_strength + away_strength,
            league_factor, home_attack - away_defence, away_attack - home_defence,
        ]
        metadata = {
            "home": home_name, "away": away_name,
            "home_id": home_id, "away_id": away_id,
            "home_strength": home_strength, "away_strength": away_strength,
            "home_attack": home_attack, "home_defence": home_defence,
            "away_attack": away_attack, "away_defence": away_defence,
            "home_form": home_form, "away_form": away_form,
            "xg_home": xg_home, "xg_away": xg_away,
        }
        return features, metadata

    def predict_with_confidence(self, fixture: Dict[str, Any]) -> Dict[str, Any]:
        if fixture.get("_hibs_prediction_blocked"):
            return prediction_unavailable_payload(
                fixture,
                str(fixture.get("_hibs_prediction_block_reason") or "fixture_enrichment_failed"),
            )
        dq_pre = fixture.get("data_quality") or {}
        dq_pre_pct = float(dq_pre.get("score_pct") or 0)
        predict_dq_floor = predict_min_data_quality_pct()
        if predict_dq_floor > 0 and dq_pre_pct > 0 and dq_pre_pct < predict_dq_floor:
            return prediction_unavailable_payload(fixture, "abstained_low_dq")
        try:
            dq_abstain_floor = float(os.getenv("HIBS_ABSTAIN_DATA_PCT", "48"))
        except ValueError:
            dq_abstain_floor = 48.0
        has_book_triplet = bool(fixture.get("odds_available")) or all(
            float(fixture.get(k) or 0) > 1.0 for k in ("odds_home", "odds_draw", "odds_away")
        )
        if dq_pre_pct > 0 and dq_pre_pct < dq_abstain_floor and not has_book_triplet:
            return prediction_unavailable_payload(fixture, "data_coverage_too_thin")
        features, metadata = self.build_advanced_features(fixture)
        n_home_early = int(fixture.get("home_recent_n", 0) or 0)
        n_away_early = int(fixture.get("away_recent_n", 0) or 0)
        form_w = form_sample_weight(n_home_early, n_away_early)
        features = apply_form_weight_to_features(features, metadata, form_w)
        xg_home = float(metadata["xg_home"])
        xg_away = float(metadata["xg_away"])
        league_code = str(fixture.get("league") or "")
        xg_home, xg_away, xg_quality_dbg = adjust_xg_for_source_quality(
            xg_home,
            xg_away,
            fixture.get("xg_source"),
            league_code,
        )
        metadata["xg_home"] = xg_home
        metadata["xg_away"] = xg_away
        if os.getenv("HIBS_USE_INJURY_LAMBDA_ADJUST", "").strip().lower() in ("1", "true", "yes", "on"):
            try:
                max_cut = min(0.08, max(0.0, float(os.getenv("HIBS_INJURY_LAMBDA_MAX_CUT", "0.08"))))
            except ValueError:
                max_cut = 0.08

            def _injury_factor(avail: Any) -> float:
                try:
                    a = float(avail)
                except (TypeError, ValueError):
                    return 1.0
                a = max(0.5, min(1.0, a))
                return max(1.0 - max_cut, a)

            xg_home *= _injury_factor(fixture.get("attack_availability_home"))
            xg_away *= _injury_factor(fixture.get("attack_availability_away"))
            metadata["xg_home"] = xg_home
            metadata["xg_away"] = xg_away
        fixture = {**fixture, "xg_home": xg_home, "xg_away": xg_away}
        sup_xg_dbg: Optional[Dict[str, Any]] = None
        if os.getenv("HIBS_USE_SUPPLEMENTAL_XG_PRIOR", "1").lower() not in ("0", "false", "no", "off"):
            sup = fixture.get("supplemental") or {}
            us = sup.get("understat_light") or sup.get("understat") or {}
            u_h, u_a = us.get("xg_home"), us.get("xg_away")
            if u_h is not None and u_a is not None:
                try:
                    uh, ua = float(u_h), float(u_a)
                except (TypeError, ValueError):
                    uh = ua = 0.0
                if uh > 0.04 and ua > 0.04 and (uh + ua) < 6.0:
                    try:
                        w = float(os.getenv("HIBS_SUPPLEMENTAL_XG_BLEND", "0.1"))
                    except ValueError:
                        w = 0.1
                    w = max(0.0, min(0.3, w))
                    xg_home = xg_home * (1.0 - w) + uh * w
                    xg_away = xg_away * (1.0 - w) + ua * w
                    metadata["xg_home"] = xg_home
                    metadata["xg_away"] = xg_away
                    sup_xg_dbg = {"blend_weight": w, "understat_xg_home": uh, "understat_xg_away": ua}
        poisson_probs_raw = self._poisson_match_probs(xg_home, xg_away, league_code=league_code)
        X = np.array([features])
        try:
            rf_probs = self.rf_model.predict_proba(X)[0]
            gb_probs = self.gb_model.predict_proba(X)[0]
            ml_probs = {
                "home": float(rf_probs[0] * 0.6 + gb_probs[0] * 0.4),
                "draw": float(rf_probs[1] * 0.6 + gb_probs[1] * 0.4),
                "away": float(rf_probs[2] * 0.6 + gb_probs[2] * 0.4),
            }
        except Exception:
            if _allow_dummy_numeric():
                ml_probs = {"home": 0.33, "draw": 0.34, "away": 0.33}
            else:
                ml_probs = dict(poisson_probs_raw)
        ml_probs, ml_cal_dbg = apply_ml_isotonic_calibration(ml_probs, league_code)
        mode = self._read_1x2_mode()

        lam_cal_h: Optional[float] = None
        lam_cal_a: Optional[float] = None
        cal_dbg: Dict[str, Any] = {}
        poisson_probs_cal: Optional[Dict[str, float]] = None
        blend_w: Optional[Dict[str, float]] = None
        if mode in ("calibrated_poisson", "blend_all"):
            lam_cal_h, lam_cal_a, cal_dbg = calibrated_match_lambdas(
                xg_home,
                xg_away,
                league_code,
                fixture.get("home_position"),
                fixture.get("away_position"),
            )
            try:
                from hibs_predictor.match_insight import derive_motivation_context, _motivation_lambda_nudge

                motivation = derive_motivation_context(fixture)
                mot_h = _motivation_lambda_nudge(motivation.get("home") or [])
                mot_a = _motivation_lambda_nudge(motivation.get("away") or [])
                lam_cal_h *= mot_h
                lam_cal_a *= mot_a
                if motivation.get("labels"):
                    cal_dbg = {**cal_dbg, "motivation_labels": motivation["labels"]}
            except Exception:
                pass
            poisson_probs_cal = self._poisson_match_probs(lam_cal_h, lam_cal_a, league_code=league_code)

        if mode == "calibrated_poisson" and poisson_probs_cal is not None:
            ensemble_probs = dict(poisson_probs_cal)
        elif mode == "blend_all" and poisson_probs_cal is not None:
            w_ml, w_raw, w_cal = self._read_blend_weights()
            blend_w = {"ml": round(w_ml, 3), "poisson_raw": round(w_raw, 3), "poisson_calibrated": round(w_cal, 3)}
            merged = self._merge_three_1x2(ml_probs, poisson_probs_raw, poisson_probs_cal, w_ml, w_raw, w_cal)
            ensemble_probs = dict(merged) if merged is not None else dict(poisson_probs_raw)
        else:
            poisson_w = 0.78 if not self.is_trained else 0.6
            ml_w = 1.0 - poisson_w
            ensemble_probs = {
                k: ml_probs[k] * ml_w + poisson_probs_raw[k] * poisson_w for k in ["home", "draw", "away"]
            }
            total = sum(ensemble_probs.values())
            if total > 0:
                ensemble_probs = {k: v / total for k, v in ensemble_probs.items()}
        ensemble_probs, league_profile_debug = apply_league_probability_profile(ensemble_probs, league_code)
        cal_shrink, cal_shrink_dbg = league_shrink_for_predict(league_code)
        if abs(cal_shrink - 1.0) >= 0.001:
            ensemble_probs = apply_calibration_shrink(ensemble_probs, cal_shrink)
        matchup_context = self._matchup_context(fixture, metadata, xg_home, xg_away)
        ensemble_probs, mismatch_calibration = self._apply_mismatch_calibration(ensemble_probs, matchup_context)
        h2h_record = extract_h2h_from_recent(fixture)
        ensemble_probs, h2h_calibration = blend_h2h_into_1x2(ensemble_probs, h2h_record)
        laplace_w = laplace_1x2_model_weight()
        if laplace_w < 1.0:
            ensemble_probs = laplace_smooth_1x2(ensemble_probs, model_weight=laplace_w)
        bookmaker_odds = _best_1x2_odds_from_fixture(fixture)
        has_book = len(bookmaker_odds) == 3
        try:
            cross_pct = max(
                float(fixture.get("odds_cross_max_implied_diff_pct") or 0.0),
                float(fixture.get("odds_cross_book_max_implied_diff_pct") or 0.0),
            )
        except (TypeError, ValueError):
            cross_pct = 0.0
        sharp_impl = fixture.get("sharp_anchor_implied") or {}
        dq_pct_blend = float(dq_pre.get("score_pct") or 0)
        dq_anchor = _env_float("HIBS_DQ_SHARP_ANCHOR_PCT", 75.0)
        if (
            isinstance(sharp_impl, dict)
            and all(sharp_impl.get(s) for s in ("home", "draw", "away"))
            and dq_pct_blend > 0
            and dq_pct_blend < dq_anchor
        ):
            sharp_w = min(0.52, 0.30 + (dq_anchor - dq_pct_blend) * 0.003)
            ensemble_probs = blend_probs_toward_anchor(
                ensemble_probs,
                sharp_impl,
                sharp_w,
                keys=("home", "draw", "away"),
            )
        elif has_book and bookmaker_odds:
            try:
                blend = float(os.getenv("HIBS_CALIB_MARKET_BLEND", "0.06"))
            except ValueError:
                blend = 0.06
            blend += _friendlies_market_blend_extra(league_code)
            if dq_pct_blend >= dq_anchor:
                blend = min(blend, 0.04 + _friendlies_market_blend_extra(league_code))
            elif dq_pct_blend > 0:
                blend = min(0.12 + _friendlies_market_blend_extra(league_code), blend + (dq_anchor - dq_pct_blend) * 0.0008)
            ensemble_probs = self._blend_1x2_toward_implied(ensemble_probs, bookmaker_odds, blend)

        use_cal_side = mode == "calibrated_poisson" or (
            mode == "blend_all"
            and (os.getenv("HIBS_SIDE_MARKETS_USE_CALIBRATED", "1").lower() in ("1", "true", "yes"))
        )
        lam_h_side = float(lam_cal_h) if (use_cal_side and lam_cal_h is not None) else float(xg_home)
        lam_a_side = float(lam_cal_a) if (use_cal_side and lam_cal_a is not None) else float(xg_away)
        if not use_cal_side:
            try:
                from hibs_predictor.match_insight import derive_motivation_context, _motivation_lambda_nudge

                motivation_raw = derive_motivation_context(fixture)
                lam_h_side *= _motivation_lambda_nudge(motivation_raw.get("home") or [])
                lam_a_side *= _motivation_lambda_nudge(motivation_raw.get("away") or [])
            except Exception:
                pass

        poisson_top_scores: List[Dict[str, Any]] = []
        try:
            from hibs_predictor.match_insight import poisson_top_scorelines

            poisson_top_scores = poisson_top_scorelines(lam_h_side, lam_a_side, top_n=3)
        except Exception:
            pass

        if self._use_bivariate_side_markets():
            from hibs_predictor.bivariate_poisson import side_market_probs

            biv_side = side_market_probs(lam_h_side, lam_a_side)
            poisson_btts = float(biv_side["btts_yes"])
            over15_prob = float(biv_side["over15"])
            over25_prob = float(biv_side["over25"])
            over35_prob = float(biv_side["over35"])
            under15_prob = float(biv_side["under15"])
            under35_prob = float(biv_side["under35"])
            j_home_btts = float(biv_side["home_and_btts"])
            j_draw_btts = float(biv_side["draw_and_btts"])
            j_away_btts = float(biv_side["away_and_btts"])
        else:
            poisson_btts = self._poisson_btts_probability(lam_h_side, lam_a_side)
            over15_prob = self._poisson_over_goals_probability(lam_h_side, lam_a_side, 1.5)
            over25_prob = self._poisson_over_goals_probability(lam_h_side, lam_a_side, 2.5)
            over35_prob = self._poisson_over_goals_probability(lam_h_side, lam_a_side, 3.5)
            under15_prob = max(0.02, min(0.98, 1.0 - over15_prob))
            under35_prob = max(0.02, min(0.98, 1.0 - over35_prob))
            j_home_btts = self._poisson_joint_home_win_and_btts(lam_h_side, lam_a_side)
            j_draw_btts = self._poisson_joint_draw_and_btts(lam_h_side, lam_a_side)
            j_away_btts = self._poisson_joint_away_win_and_btts(lam_h_side, lam_a_side)
        hb = float(fixture.get("home_btts_rate", 0.0) or 0.0)
        ab = float(fixture.get("away_btts_rate", 0.0) or 0.0)
        empirical_btts = (hb + ab) / 2.0 if (hb > 0 or ab > 0) else 0.0
        n_home = int(fixture.get("home_recent_n", 0) or 0)
        n_away = int(fixture.get("away_recent_n", 0) or 0)
        if n_home >= 4 and n_away >= 4:
            btts_prob = max(0.03, min(0.97, poisson_btts * 0.42 + empirical_btts * 0.58))
        elif n_home >= 2 or n_away >= 2:
            w = 0.65
            btts_prob = max(0.03, min(0.97, poisson_btts * w + empirical_btts * (1.0 - w)))
        else:
            btts_prob = poisson_btts
        merged_model = {
            **ensemble_probs,
            "btts_yes": btts_prob,
            "btts_no": max(0.02, min(0.98, 1.0 - btts_prob)),
            "over15": over15_prob,
            "under15": under15_prob,
            "over25": over25_prob,
            "under25": max(0.02, min(0.98, 1.0 - over25_prob)),
            "over35": over35_prob,
            "under35": under35_prob,
            "home_and_btts": j_home_btts,
            "draw_and_btts": j_draw_btts,
            "away_and_btts": j_away_btts,
        }
        merged_book: Dict[str, float] = {}
        if bookmaker_odds:
            for k, v in bookmaker_odds.items():
                if v is not None and float(v) > 1.0:
                    merged_book[str(k)] = float(v)
        mo = fixture.get("market_odds") or {}
        bt = mo.get("btts") or {}
        if bt.get("yes") and float(bt["yes"]) > 1.0:
            merged_book["btts_yes"] = float(bt["yes"])
        if bt.get("no") and float(bt["no"]) > 1.0:
            merged_book["btts_no"] = float(bt["no"])
        to = mo.get("totals_2_5") or {}
        if to.get("over") and float(to["over"]) > 1.0:
            merged_book["over25"] = float(to["over"])
        if to.get("under") and float(to["under"]) > 1.0:
            merged_book["under25"] = float(to["under"])
        to15 = mo.get("totals_1_5") or {}
        if to15.get("over") and float(to15["over"]) > 1.0:
            merged_book["over15"] = float(to15["over"])
        if to15.get("under") and float(to15["under"]) > 1.0:
            merged_book["under15"] = float(to15["under"])
        to35 = mo.get("totals_3_5") or {}
        if to35.get("over") and float(to35["over"]) > 1.0:
            merged_book["over35"] = float(to35["over"])
        if to35.get("under") and float(to35["under"]) > 1.0:
            merged_book["under35"] = float(to35["under"])
        dq_bundle = fixture.get("data_quality") or {}
        dq_pct = float(dq_bundle.get("score_pct") or 0)
        n_home_venue, n_away_venue = venue_form_sample_counts(fixture)
        bet_confidence = compute_bet_confidence(
            dq_pct,
            n_home_early,
            n_away_early,
            fixture.get("xg_source"),
            n_home_venue=n_home_venue,
            n_away_venue=n_away_venue,
        )
        bet_conf_min = min_bet_confidence_for_value()
        bet_conf_ok = bet_confidence >= bet_conf_min
        try:
            dq_min_boost = float(os.getenv("HIBS_MIN_DATA_QUALITY_PCT", "58"))
        except ValueError:
            dq_min_boost = 58.0
        dq_val_req = _env_float("HIBS_VALUE_REQUIRE_DATA_PCT", 78.0)
        base_margin = _env_float("HIBS_VALUE_EDGE_MARGIN", 0.05)
        cup_dq_floor = _env_float("HIBS_VALUE_CUP_DQ_PCT", 82.0)
        avg_n = (n_home + n_away) / 2.0
        conf_scale = min(1.0, max(0.4, avg_n / 8.0))
        margin = base_margin + (1.0 - conf_scale) * 0.02
        margin += value_margin_extra(league_code, dq_pct)
        margin += _friendlies_value_margin_extra(league_code)
        margin += _gate_league_margin_delta(league_code)
        margin = max(0.03, min(0.09, margin))
        if dq_min_boost > 0 and dq_pct < dq_min_boost:
            margin *= 1.0 + min(0.35, (dq_min_boost - dq_pct) / 100.0)
        margin = min(0.14, margin)
        value_bets = OddsAnalyzer.identify_value_bets(merged_model, merged_book, margin=margin) if merged_book else {}
        dq_known = bool(dq_bundle and dq_bundle.get("score_pct") is not None)
        markets_enabled = _value_markets_enabled()
        league_code_val = str(fixture.get("league") or league_code or "")
        portfolio_reject: Dict[str, str] = {}
        if not _value_league_allowed(league_code_val):
            portfolio_reject = {k: "league_not_in_value_allowlist" for k in value_bets}
            value_bets = {}
        elif _is_cup_or_playoff_fixture(fixture) and dq_known and dq_pct < cup_dq_floor:
            portfolio_reject = {k: "cup_playoff_low_data_quality" for k in value_bets}
            value_bets = {}
        else:
            fr_dq = _friendlies_value_dq_floor(league_code_val)
            if fr_dq > 0 and dq_known and dq_pct < fr_dq:
                portfolio_reject = {k: "friendlies_data_quality_floor" for k in value_bets}
                value_bets = {}
        filtered_value_bets, rejected_value_bets = self._filter_value_bets(
            value_bets,
            fixture,
            merged_model,
            matchup_context,
            margin,
            dq_pct,
            dq_known,
            markets_enabled=markets_enabled,
            cross_pct=cross_pct,
            xg_source=fixture.get("xg_source"),
            bet_confidence=bet_confidence,
        )
        if portfolio_reject:
            rejected_value_bets = {**portfolio_reject, **rejected_value_bets}
        value_bets = filtered_value_bets
        gated_values = dq_val_req > 0 and dq_pct < dq_val_req
        if gated_values:
            value_bets = {}
            rejected_value_bets = {**{k: "data_quality_env_gate" for k in filtered_value_bets}, **rejected_value_bets}
        elif not bet_conf_ok and value_bets:
            rejected_value_bets = {
                **{k: "bet_confidence_below_floor" for k in value_bets},
                **rejected_value_bets,
            }
            value_bets = {}

        book_1x2 = dict(bookmaker_odds) if bookmaker_odds else {}
        for _k, _row in value_bets.items():
            _odds = self._safe_float(_row.get("odds"), 0.0) or 0.0
            _row["source"] = "model_edge"
            _row["value_tier"] = _value_odds_class(str(_k), _odds, book_1x2)

        value_bets_alt: Dict[str, Any] = {}
        alt_rejected: Dict[str, str] = {}
        if not gated_values and not portfolio_reject and bet_conf_ok:
            sharp_impl = fixture.get("sharp_anchor_implied") or {}
            alt_raw = (
                OddsAnalyzer.identify_market_consensus_value(
                    ensemble_probs,
                    sharp_impl,
                    book_1x2,
                    margin=_value_consensus_margin(),
                    min_model_prob=_value_consensus_min_model(),
                )
                if sharp_impl and book_1x2
                else {}
            )
            alt_filtered, alt_rejected = self._filter_value_bets(
                alt_raw,
                fixture,
                merged_model,
                matchup_context,
                margin,
                dq_pct,
                dq_known,
                markets_enabled=markets_enabled,
                cross_pct=cross_pct,
                xg_source=fixture.get("xg_source"),
                bet_confidence=bet_confidence,
            )
            for _k, _row in alt_filtered.items():
                row = dict(_row)
                row["source"] = "market_consensus"
                row["value_tier"] = _value_odds_class(
                    str(_k), self._safe_float(row.get("odds"), 0.0) or 0.0, book_1x2
                )
                value_bets_alt[_k] = row
                if _k in value_bets:
                    value_bets[_k]["value_dual_agree"] = True
                    row["value_dual_agree"] = True

        if poisson_probs_cal and book_1x2:
            for _pk in ("home", "draw", "away"):
                if _pk not in value_bets:
                    continue
                poisson_p = float(poisson_probs_cal.get(_pk, 0.0))
                odds_pk = book_1x2.get(_pk)
                if not odds_pk or float(odds_pk) <= 1.0:
                    continue
                impl_pk = OddsAnalyzer.decimal_to_probability(float(odds_pk))
                if poisson_p - impl_pk > margin and poisson_p >= _value_consensus_min_model():
                    value_bets[_pk]["poisson_agree"] = True
        confidence = max(ensemble_probs.values())
        confidence = confidence_display_scale(confidence, n_home_early, n_away_early)
        try:
            from hibs_predictor.lineup_enrich import lineup_confidence_multiplier

            confidence *= lineup_confidence_multiplier(fixture)
        except Exception:
            pass
        predicted_outcome = max(ensemble_probs, key=ensemble_probs.get)
        best_bet = max(value_bets, key=lambda x: value_bets[x].get("roi_percent", 0)) if value_bets else None
        best_roi = value_bets[best_bet].get("roi_percent", 0.0) if best_bet else 0.0
        market_labels = {
            "home": "1X2 Home",
            "draw": "1X2 Draw",
            "away": "1X2 Away",
            "btts_yes": "BTTS Yes",
            "btts_no": "BTTS No",
            "over15": "Over 1.5",
            "under15": "Under 1.5",
            "over25": "Over 2.5",
            "under25": "Under 2.5",
            "over35": "Over 3.5",
            "under35": "Under 3.5",
            "home_and_btts": "Home + BTTS",
            "draw_and_btts": "Draw + BTTS",
            "away_and_btts": "Away + BTTS",
        }
        for _k, row in value_bets.items():
            row["market_label"] = market_labels.get(_k, _k.replace("_", " ").title())
        for _k, row in value_bets_alt.items():
            row["market_label"] = market_labels.get(_k, _k.replace("_", " ").title())
        for _ti, (_k, _row) in enumerate(sorted(value_bets.items(), key=lambda kv: -kv[1].get("roi_percent", 0.0))):
            _row["value_rank"] = 1 if _ti == 0 else (2 if _ti == 1 else 3)
        value_highlights = sorted(
            [
                {
                    "key": k,
                    "roi": v.get("roi_percent", 0.0),
                    "label": v.get("market_label", k),
                    "tier": int(v.get("value_rank", 3)),
                    "value_tier": v.get("value_tier"),
                    "source": v.get("source"),
                }
                for k, v in value_bets.items()
            ],
            key=lambda z: -z["roi"],
        )[:6]
        value_signals: List[Dict[str, Any]] = []
        seen_signal: set = set()
        for k, v in sorted(value_bets.items(), key=lambda kv: -kv[1].get("roi_percent", 0.0)):
            if k in seen_signal:
                continue
            sig = dict(v)
            sig["outcome"] = k
            value_signals.append(sig)
            seen_signal.add(k)
        for k, v in sorted(value_bets_alt.items(), key=lambda kv: -kv[1].get("roi_percent", 0.0)):
            if k in seen_signal:
                continue
            sig = dict(v)
            sig["outcome"] = k
            value_signals.append(sig)
            seen_signal.add(k)
        value_bets_display: List[Dict[str, Any]] = []
        seen_display: set = set()
        for k, v in sorted(value_bets.items(), key=lambda kv: -kv[1].get("roi_percent", 0.0)):
            if k in seen_display:
                continue
            row = dict(v)
            row["outcome"] = k
            value_bets_display.append(row)
            seen_display.add(k)
        for k, v in sorted(value_bets_alt.items(), key=lambda kv: -kv[1].get("roi_percent", 0.0)):
            if k in seen_display:
                continue
            row = dict(v)
            row["outcome"] = k
            value_bets_display.append(row)
            seen_display.add(k)
        line_odds: Dict[str, Any] = {}
        for _lk in ("btts_yes", "btts_no", "over15", "under15", "over25", "under25", "over35", "under35"):
            _lv = merged_book.get(_lk)
            try:
                _fv = float(_lv)
                line_odds[_lk] = round(_fv, 2) if _fv > 1.0 else None
            except (TypeError, ValueError):
                line_odds[_lk] = None
        sup = fixture.get("supplemental") or {}
        hsk = sup.get("heavy_skipped") or {}
        dq = fixture.get("data_quality") or {}
        sup_errs = [k for k in sup if str(k).endswith("_error")]
        score_pct = float(dq.get("score_pct") or 0)
        if hsk.get("reason") == "api_strong_skip_heavy":
            pq_summary = "API coverage is strong for this fixture; heavy HTML scrapers were skipped — 1X2 unchanged by FBref/Understat."
        elif score_pct < 70:
            pq_summary = "Lower data coverage; treat multi-market and value hints cautiously."
        elif sup_errs:
            pq_summary = "Some supplemental sources failed; core prediction still uses APIs + Poisson/ML blend."
        else:
            pq_summary = "Typical input mix for this fixture."

        out: Dict[str, Any] = {
            "fixture": f"{metadata['home']} vs {metadata['away']}",
            "home": metadata["home"], "away": metadata["away"],
            "probabilities": {k: round(v, 4) for k, v in ensemble_probs.items()},
            "probabilities_pct": {k: round(v * 100, 1) for k, v in ensemble_probs.items()},
            "predicted_outcome": predicted_outcome,
            "confidence": round(confidence, 4),
            "confidence_pct": round(confidence * 100, 1),
            "bookmaker_odds": bookmaker_odds if bookmaker_odds else {"home": None, "draw": None, "away": None},
            "odds_source_bookmaker": has_book,
            "value_bets": value_bets,
            "value_bets_alt": value_bets_alt,
            "value_signals": value_signals,
            "value_bets_alt_rejected": alt_rejected,
            "value_bets_display": value_bets_display,
            "value_highlights": value_highlights,
            "line_odds": line_odds,
            "has_any_value": bool(value_bets) or bool(value_bets_alt),
            "best_bet": best_bet,
            "best_bet_roi": round(best_roi, 1),
            "data_quality": dq_bundle if dq_bundle else None,
            "xg_source": fixture.get("xg_source"),
            "value_bets_gated_by_data": gated_values,
            "value_bets_rejected": rejected_value_bets,
            "value_sharpen_gates_enabled": _sharpen_gates_enabled(),
            "value_away_tighten_enabled": _away_tighten_enabled(),
            "value_under_tighten_enabled": _under_tighten_enabled(),
            "value_edge_margin_used": round(margin, 4),
            "score_and_btts_pct": {
                "home_win_and_btts": round(j_home_btts * 100, 1),
                "draw_and_btts": round(j_draw_btts * 100, 1),
                "away_win_and_btts": round(j_away_btts * 100, 1),
            },
            "odds_cross_max_implied_diff_pct": float(fixture.get("odds_cross_max_implied_diff_pct") or 0.0),
            "expected_goals_home": round(xg_home, 2),
            "expected_goals_away": round(xg_away, 2),
            "btts_probability": round(btts_prob, 4),
            "btts_probability_pct": round(btts_prob * 100, 1),
            "over15_probability_pct": round(over15_prob * 100, 1),
            "over25_probability_pct": round(over25_prob * 100, 1),
            "over35_probability_pct": round(over35_prob * 100, 1),
            "team_strength_home": round(metadata["home_strength"] * 100, 1),
            "team_strength_away": round(metadata["away_strength"] * 100, 1),
            "form_home": round(metadata["home_form"] * 100, 1),
            "form_away": round(metadata["away_form"] * 100, 1),
            "poisson_probs": {k: round(v * 100, 1) for k, v in poisson_probs_raw.items()},
            "ml_probs_pct": {k: round(float(ml_probs.get(k, 0.0)) * 100, 1) for k in ("home", "draw", "away")},
            "ml_isotonic_calibration": ml_cal_dbg,
            "side_markets_model": "bivariate_poisson" if self._use_bivariate_side_markets() else "independent_poisson",
            "one_x2_mode": mode,
            "supplemental_xg_prior": sup_xg_dbg,
            "prediction_quality_hint": {
                "data_score_pct": dq.get("score_pct"),
                "full_scope": dq.get("full_scope"),
                "supplemental_errors": sup_errs[:10],
                "heavy_scrape": (
                    "skipped:" + str(hsk.get("reason"))
                    if hsk.get("reason")
                    else (
                        "used"
                        if sup.get("understat") or sup.get("fbref_home_squad")
                        else "not_run"
                    )
                ),
                "summary": pq_summary,
            },
            "lambda_side_home": round(lam_h_side, 3),
            "lambda_side_away": round(lam_a_side, 3),
            "lambda_calibration": cal_dbg,
            "matchup_calibration": mismatch_calibration,
            "league_model_profile": league_profile_debug,
            "historic_calibration": {
                "calibration_shrink": cal_shrink_dbg,
                "dixon_coles_rho": resolve_dixon_coles_rho(
                    league_code, xg_home=xg_home, xg_away=xg_away
                )[1],
                "xg_quality": xg_quality_dbg,
                "h2h": h2h_calibration,
                "form_sample_weight": round(form_w, 3),
            },
            "bet_confidence": bet_confidence,
            "bet_confidence_min_value": bet_conf_min,
            "blend_weights_1x2": blend_w,
            "poisson_probs_calibrated_pct": (
                {k: round(v * 100, 1) for k, v in poisson_probs_cal.items()} if poisson_probs_cal else None
            ),
            "poisson_top_scores": poisson_top_scores,
        }
        try:
            from hibs_predictor.match_insight import attach_structured_insight

            attach_structured_insight(fixture, out)
        except Exception:
            pass
        try:
            from hibs_predictor.prediction_log import maybe_log_prediction_snapshot

            maybe_log_prediction_snapshot(fixture, out)
        except Exception:
            pass
        return out

    def train(self, X_train: List[List[float]], y_train: List[int]) -> Tuple[float, float]:
        X_scaled = self.scaler.fit_transform(X_train)
        self.rf_model.fit(X_scaled, y_train)
        self.gb_model.fit(X_scaled, y_train)
        self.is_trained = True
        return self.rf_model.score(X_scaled, y_train), self.gb_model.score(X_scaled, y_train)


def portfolio_kickoff_window_minutes() -> int:
    try:
        return max(1, int(os.getenv("HIBS_PORTFOLIO_KICKOFF_WINDOW_MIN", "60")))
    except ValueError:
        return 60


def portfolio_stake_cap_pct() -> float:
    return max(0.0, _env_float("HIBS_PORTFOLIO_STAKE_CAP_PCT", 10.0))


def _fixture_kickoff_dt(fixture: Dict[str, Any]) -> Optional[datetime]:
    raw = fixture.get("kickoff_sort") or fixture.get("date")
    if not raw:
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            from datetime import timezone

            return dt.replace(tzinfo=timezone.utc)
        return dt
    except (TypeError, ValueError):
        return None


def _value_bet_kelly_percent(row: Dict[str, Any]) -> float:
    kelly = row.get("kelly") if isinstance(row.get("kelly"), dict) else {}
    try:
        return float(kelly.get("suggested_percent") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _kelly_label_and_explanation(suggested_percent: float) -> Tuple[str, str]:
    example_stake = round(suggested_percent, 2)
    if suggested_percent >= 5.0:
        return (
            "Strong",
            f"Strong edge. Stake ~{suggested_percent:.1f}% of bankroll (e.g. \u00a3{example_stake:.2f} per \u00a3100).",
        )
    if suggested_percent >= 2.5:
        return (
            "Moderate",
            f"Moderate edge. Stake ~{suggested_percent:.1f}% of bankroll (e.g. \u00a3{example_stake:.2f} per \u00a3100).",
        )
    if suggested_percent > 0:
        return (
            "Cautious",
            f"Small edge. Stake ~{suggested_percent:.1f}% of bankroll (e.g. \u00a3{example_stake:.2f} per \u00a3100).",
        )
    return "Skip", "No positive edge \u2014 skip this bet."


def _apply_portfolio_kelly_row(
    row: Dict[str, Any],
    scaled_percent: float,
    *,
    window_n: int,
    cap_scaled: bool,
) -> None:
    kelly = row.setdefault("kelly", {})
    if kelly.get("portfolio_kelly_original_pct") is None:
        kelly["portfolio_kelly_original_pct"] = round(_value_bet_kelly_percent(row), 1)
    scaled_percent = round(max(0.0, scaled_percent), 1)
    kelly["suggested_percent"] = scaled_percent
    kelly["portfolio_window_n"] = window_n
    kelly["portfolio_cap_scaled"] = bool(cap_scaled)
    label, explanation = _kelly_label_and_explanation(scaled_percent)
    kelly["confidence_label"] = label
    kelly["explanation"] = explanation
    kelly["example_stake"] = f"\u00a3{scaled_percent:.2f}"


def _portfolio_fixture_key(fixture: Dict[str, Any]) -> str:
    fid = fixture.get("id") or fixture.get("fixture_id")
    if fid is not None:
        return str(fid)
    home = fixture.get("home")
    away = fixture.get("away")
    if isinstance(home, dict):
        home = home.get("name")
    if isinstance(away, dict):
        away = away.get("name")
    ko = fixture.get("kickoff_sort") or fixture.get("date") or ""
    return f"{home}|{away}|{ko}"


def apply_portfolio_kelly(fixtures: List[Dict[str, Any]]) -> None:
    """
    Portfolio Kelly: joint sqrt(k) within the same fixture, then sqrt(N) across independent
    matches in a kickoff window, with a total window stake cap.
    """
    if not fixtures:
        return
    window_min = portfolio_kickoff_window_minutes()
    cap = portfolio_stake_cap_pct()
    entries: List[Dict[str, Any]] = []
    for fx in fixtures:
        pred = fx.get("prediction")
        if not isinstance(pred, dict):
            continue
        ko = _fixture_kickoff_dt(fx)
        if ko is None:
            continue
        fx_key = _portfolio_fixture_key(fx)
        for pool_name in ("value_bets", "value_bets_alt"):
            pool = pred.get(pool_name)
            if not isinstance(pool, dict):
                continue
            for outcome, row in pool.items():
                if not isinstance(row, dict):
                    continue
                pct = _value_bet_kelly_percent(row)
                if pct <= 0:
                    continue
                entries.append(
                    {
                        "kickoff": ko,
                        "row": row,
                        "outcome": str(outcome),
                        "pool": pool_name,
                        "fixture_key": fx_key,
                    }
                )

    if not entries:
        return

    by_fixture: Dict[str, List[Dict[str, Any]]] = {}
    for ent in entries:
        by_fixture.setdefault(ent["fixture_key"], []).append(ent)

    for fx_key, group in by_fixture.items():
        k = len(group)
        if k <= 1:
            continue
        denom = math.sqrt(float(k))
        for ent in group:
            ent["match_scaled_pct"] = _value_bet_kelly_percent(ent["row"]) / denom
            ent["portfolio_match_legs"] = k

    for ent in entries:
        if "match_scaled_pct" not in ent:
            ent["match_scaled_pct"] = _value_bet_kelly_percent(ent["row"])
            ent["portfolio_match_legs"] = 1

    entries.sort(key=lambda e: e["kickoff"])
    clusters: List[List[Dict[str, Any]]] = []
    cluster: List[Dict[str, Any]] = []
    cluster_start: Optional[datetime] = None
    for ent in entries:
        if not cluster:
            cluster = [ent]
            cluster_start = ent["kickoff"]
            continue
        assert cluster_start is not None
        if (ent["kickoff"] - cluster_start).total_seconds() <= window_min * 60:
            cluster.append(ent)
        else:
            clusters.append(cluster)
            cluster = [ent]
            cluster_start = ent["kickoff"]
    if cluster:
        clusters.append(cluster)

    for group in clusters:
        fixture_keys = {ent["fixture_key"] for ent in group}
        n_matches = max(1, len(fixture_keys))
        denom = math.sqrt(float(n_matches))
        scaled_pcts = [float(ent["match_scaled_pct"]) / denom for ent in group]
        total = sum(scaled_pcts)
        factor = 1.0
        if cap > 0 and total > cap:
            factor = cap / total
        cap_scaled = factor < 0.999
        for ent, pct in zip(group, scaled_pcts):
            _apply_portfolio_kelly_row(
                ent["row"],
                pct * factor,
                window_n=n_matches,
                cap_scaled=cap_scaled,
            )
            kelly = ent["row"].setdefault("kelly", {})
            kelly["portfolio_match_legs"] = int(ent.get("portfolio_match_legs") or 1)
