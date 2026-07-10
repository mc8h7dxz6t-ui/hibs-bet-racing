"""Deep enrichment hooks — safe defaults; uses football_data_requests_allowed guard."""

from __future__ import annotations

import os
from datetime import date, datetime, timezone
from typing import Any, Dict, List

from hibs_predictor.api_clients import football_data_requests_allowed
from hibs_predictor.config import LEAGUES
from hibs_predictor.data_quality import compute_fixture_data_quality


def football_data_standings_allowed() -> bool:
    """Backward-compatible alias for stale VPS modules."""
    return football_data_requests_allowed()


def _env_truthy(name: str, default: str = "0") -> bool:
    return (os.getenv(name, default) or "").strip().lower() in ("1", "true", "yes", "on")


def deep_enrich_today_only() -> bool:
    return _env_truthy("HIBS_DEEP_ENRICH_TODAY_ONLY")


def fixture_is_today(fixture: Dict[str, Any]) -> bool:
    raw = str(fixture.get("date") or fixture.get("kickoff") or "").strip()
    if not raw:
        return False
    try:
        text = raw.replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).date() == datetime.now(timezone.utc).date()
    except ValueError:
        return raw[:10] == date.today().isoformat()


def _dq_score(enriched: Dict[str, Any]) -> float:
    dq = enriched.get("data_quality") if isinstance(enriched.get("data_quality"), dict) else {}
    try:
        return float(dq.get("score_pct") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def deep_enrich_plan(fixture: Dict[str, Any], league_code: str, enriched: Dict[str, Any]) -> bool:
    if not _env_truthy("HIBS_DEEP_ENRICH", "1"):
        return False
    if deep_enrich_today_only() and not fixture_is_today(fixture):
        return False
    target = float(os.getenv("HIBS_DEEP_ENRICH_MIN_DQ", "55") or 55)
    return _dq_score(enriched) < target


def maybe_deep_enrich(
    aggregator: Any,
    fixture: Dict[str, Any],
    league_code: str,
    enriched: Dict[str, Any],
) -> Dict[str, Any]:
    if not deep_enrich_plan(fixture, league_code, enriched):
        return enriched
    out = dict(enriched)
    league = LEAGUES.get(league_code) or {}
    fdo_comp = league.get("football_data_org_id")
    clients = getattr(aggregator, "clients", {}) or {}
    if fdo_comp and "football_data_org" in clients and football_data_requests_allowed():
        season = int(fixture.get("season") or datetime.now(timezone.utc).year)
        client = clients["football_data_org"]
        from hibs_predictor.fixture_utils import fixture_team_id

        for side, key in (("home", "home_position"), ("away", "away_position")):
            if out.get(key):
                continue
            team_id = fixture_team_id(fixture, side)
            if not team_id:
                continue
            try:
                row = client.fetch_team_position(int(team_id), str(fdo_comp), season)
                if row:
                    out[key] = row
            except Exception:
                pass
    out["data_quality"] = compute_fixture_data_quality(out)
    return out


def league_codes_priority_xg_gaps(codes: List[str]) -> List[str]:
    nordic = {"SWEDEN_ALLSVENSKAN", "NORWAY_ELITESERIEN", "FINLAND_VEIKKAUSLIIGA", "DENMARK_SUPERLIGA"}
    front = [c for c in codes if c in nordic]
    rest = [c for c in codes if c not in nordic]
    return front + rest


def league_codes_priority_today(
    codes: List[str],
    preview: Dict[str, List[Dict[str, Any]]],
) -> List[str]:
    def has_today(code: str) -> bool:
        rows = preview.get(code) or []
        return any(fixture_is_today(row) for row in rows if isinstance(row, dict))

    today_codes = [c for c in codes if has_today(c)]
    other = [c for c in codes if c not in today_codes]
    return today_codes + other


def reboost_dashboard_data_quality(aggregator: Any, all_fixtures: List[Dict[str, Any]]) -> int:
    if not _env_truthy("HIBS_BUNDLE_DQ_REBOOST"):
        return 0
    upgraded = 0
    for row in all_fixtures:
        if not isinstance(row, dict):
            continue
        league_code = str(row.get("league") or "")
        before = _dq_score(row)
        if before >= float(os.getenv("HIBS_DEEP_ENRICH_MIN_DQ", "55") or 55):
            continue
        try:
            after_row = maybe_deep_enrich(aggregator, row, league_code, row)
            if _dq_score(after_row) > before:
                row.update(after_row)
                upgraded += 1
        except Exception:
            continue
    return upgraded
