"""Public read-only lines export for Football Value Engine (FVE upstream).

Env (hibs-bet .env):
    FVE_LINES_TOKEN=optional-shared-secret
"""

from __future__ import annotations

import os
from typing import Any, Callable, Dict, Optional

from flask import Flask, jsonify, request


def _token_ok() -> bool:
    expected = (os.environ.get("FVE_LINES_TOKEN") or "").strip()
    if not expected:
        return True
    supplied = (
        (request.headers.get("Authorization") or "").removeprefix("Bearer ").strip()
        or (request.headers.get("X-FVE-Lines-Token") or "").strip()
    )
    return supplied == expected


def _norm_label(home: str, away: str) -> str:
    return f"{home.strip()} v {away.strip()}"


def _fixture_packet(row: Dict[str, Any]) -> Dict[str, Any]:
    home = str(row.get("home_team") or row.get("home") or "").strip()
    away = str(row.get("away_team") or row.get("away") or "").strip()
    best = row.get("best_odds_1x2") or {}
    pred = row.get("prediction") if isinstance(row.get("prediction"), dict) else {}
    probs = pred.get("probabilities") if isinstance(pred.get("probabilities"), dict) else {}
    model_probs = {
        "home": probs.get("home"),
        "draw": probs.get("draw"),
        "away": probs.get("away"),
    }
    edge_bps = _edge_bps_overlay(model_probs, best)
    return {
        "fixture_key": _norm_label(home, away),
        "fixture_id": row.get("fixture_id") or row.get("id"),
        "home_team": home,
        "away_team": away,
        "kickoff_iso": row.get("kickoff_iso") or row.get("date"),
        "best_odds_1x2": best,
        "model_probabilities_1x2": model_probs,
        "hibs_edge_bps": edge_bps,
        "best_odds_source": row.get("best_odds_source") or {},
        "home_stats": row.get("home_stats") or {},
        "away_stats": row.get("away_stats") or {},
        "league": row.get("league") or row.get("league_code"),
    }


def _edge_bps_overlay(model: Dict[str, Any], best: Dict[str, Any]) -> Dict[str, Optional[float]]:
    """Model implied vs best available odds — positive bps = hibs edge on that side."""
    out: Dict[str, Optional[float]] = {"home": None, "draw": None, "away": None}
    for side in out:
        try:
            mp = float(model.get(side) or 0)
            od = float(best.get(side) or 0)
        except (TypeError, ValueError):
            continue
        if mp <= 0 or od <= 1:
            continue
        out[side] = round((mp * od - 1.0) * 10000.0, 1)
    return out


def _find_fixture(bundle: Dict[str, Any], fixture_key: str) -> Optional[Dict[str, Any]]:
    target = fixture_key.strip().casefold()
    for row in bundle.get("all") or []:
        if not isinstance(row, dict):
            continue
        home = str(row.get("home_team") or row.get("home") or "").strip()
        away = str(row.get("away_team") or row.get("away") or "").strip()
        label = _norm_label(home, away)
        if label.casefold() == target:
            return row
    return None


def list_fixtures_peek(*, include_domestic: bool = False) -> Dict[str, Any]:
    """Read-only fixture index from disk cache — no cold-start refresh scheduling."""
    from hibs_predictor.cache import Cache
    from hibs_predictor.web import _all_fixtures_cache_key, _is_complete_fixture_bundle

    cache = Cache()
    cached = cache.peek(_all_fixtures_cache_key(include_domestic=include_domestic))
    if not isinstance(cached, dict) or not _is_complete_fixture_bundle(cached):
        return {"ok": True, "fixtures": [], "count": 0, "source": "cache_miss"}
    fixtures = []
    for row in cached.get("all") or []:
        if not isinstance(row, dict):
            continue
        home = str(row.get("home_team") or row.get("home") or "").strip()
        away = str(row.get("away_team") or row.get("away") or "").strip()
        if not home or not away:
            continue
        fixtures.append(
            {
                "fixture_key": _norm_label(home, away),
                "home_team": home,
                "away_team": away,
                "kickoff_iso": row.get("kickoff_iso") or row.get("date"),
                "league": row.get("league") or row.get("league_code"),
                "best_odds_1x2": row.get("best_odds_1x2") or {},
            }
        )
    return {"ok": True, "fixtures": fixtures, "count": len(fixtures), "source": "disk_peek"}


def build_lines_payload(bundle_loader: Callable[[], Dict[str, Any]], fixture_key: str) -> Dict[str, Any]:
    bundle = bundle_loader()
    row = _find_fixture(bundle, fixture_key)
    if not row:
        return {"ok": False, "error": "fixture_not_found", "fixture_key": fixture_key}
    pkt = _fixture_packet(row)
    pkt["ok"] = True
    return pkt


def register_fve_lines_routes(app: Flask, *, bundle_loader: Callable[[], Dict[str, Any]] | None = None) -> None:
    """Register GET /api/fve/lines/<fixture_key> on the Flask app."""

    def _loader() -> Dict[str, Any]:
        if bundle_loader is not None:
            return bundle_loader()
        from hibs_predictor.cache import Cache
        from hibs_predictor.web import _all_fixtures_cache_key, _is_complete_fixture_bundle

        cache = Cache()
        cached = cache.peek(_all_fixtures_cache_key(include_domestic=False))
        if isinstance(cached, dict) and _is_complete_fixture_bundle(cached):
            return cached
        return {"all": [], "source": "cache_miss"}

    @app.route("/api/fve/fixtures", methods=["GET"])
    def api_fve_fixtures():
        if not _token_ok():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        domestic = request.args.get("domestic", "0") == "1"
        return jsonify(list_fixtures_peek(include_domestic=domestic))

    @app.route("/api/fve/lines/<path:fixture_key>", methods=["GET"])
    def api_fve_lines(fixture_key: str):
        if not _token_ok():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        payload = build_lines_payload(_loader, fixture_key)
        if not payload.get("ok"):
            return jsonify(payload), 404
        return jsonify(payload)
