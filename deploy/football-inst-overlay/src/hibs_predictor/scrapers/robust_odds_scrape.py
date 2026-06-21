"""Robust odds rescue for scrape-first / low-quota football paths."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from hibs_predictor.fixture_utils import fixture_team_name


def _env_truthy(name: str, default: str = "1") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


def odds_rescue_enabled() -> bool:
    return _env_truthy("HIBS_ODDS_THIN_RESCUE", "1") and _env_truthy("HIBS_ROBUST_ODDS_SCRAPE", "1")


def fixture_needs_odds(row: Dict[str, Any]) -> bool:
    from hibs_predictor.scrapers.odds_thin_rescue import bundle_needs_odds_rescue

    return bundle_needs_odds_rescue(row)


def odds_coverage_summary(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(rows)
    with_odds = 0
    thin = 0
    sources: Dict[str, int] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get("odds_available"):
            with_odds += 1
        elif fixture_needs_odds(row):
            thin += 1
        src = str(row.get("odds_primary_source") or "none")
        sources[src] = sources.get(src, 0) + 1
    pct = round(100.0 * with_odds / total, 1) if total else 0.0
    min_pct = float(os.getenv("HIBS_ODDS_COVERAGE_MIN_PCT", "40"))
    return {
        "total": total,
        "with_odds": with_odds,
        "thin": thin,
        "coverage_pct": pct,
        "min_pct": min_pct,
        "ok": pct >= min_pct if total else False,
        "sources": sources,
    }


def rescue_fixture_odds(
    aggregator: Any,
    fixture: Dict[str, Any],
    league_code: str,
    *,
    enriched: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Apply odds thin rescue on one fixture; returns merged enriched dict."""
    from hibs_predictor.scrapers.odds_thin_rescue import apply_odds_thin_rescue

    base = dict(enriched or fixture)
    if not odds_rescue_enabled():
        return base
    if not fixture_needs_odds(base):
        return base

    bundle = {
        "odds_home": base.get("odds_home"),
        "odds_draw": base.get("odds_draw"),
        "odds_away": base.get("odds_away"),
        "odds_available": base.get("odds_available"),
        "all_bookmaker_odds": base.get("all_bookmaker_odds") or [],
        "odds_primary_source": base.get("odds_primary_source") or "partial",
        "odds_thin_rescue": base.get("odds_thin_rescue"),
    }
    try:
        from hibs_predictor.scrapers.scrape_resilience import resilient_call

        merged = resilient_call(
            "odds_api",
            lambda: apply_odds_thin_rescue(aggregator, fixture, league_code, bundle),
            operation="odds_thin_rescue",
            max_retries=2,
            skip_if_open=False,
        )
    except Exception:
        from hibs_predictor.scrapers.odds_thin_rescue import apply_odds_thin_rescue

        merged = apply_odds_thin_rescue(aggregator, fixture, league_code, bundle)

    out = dict(base)
    for key in (
        "odds_home",
        "odds_draw",
        "odds_away",
        "odds_available",
        "all_bookmaker_odds",
        "odds_primary_source",
        "odds_thin_rescue",
        "best_odds_1x2",
        "best_odds_source",
    ):
        if key in merged and merged.get(key) is not None:
            out[key] = merged[key]
    return out


def run_odds_rescue_pass(
    aggregator: Any,
    rows: List[Dict[str, Any]],
    *,
    max_per_cycle: Optional[int] = None,
) -> Dict[str, Any]:
    """Batch odds rescue for enriched fixtures missing 1X2."""
    if not rows:
        return {"rescued": 0, "still_thin": 0, "coverage": odds_coverage_summary([])}

    cap = max_per_cycle
    if cap is None:
        try:
            cap = max(1, int(os.getenv("HIBS_ODDS_RESCUE_MAX", "40")))
        except ValueError:
            cap = 40

    rescued = 0
    still_thin = 0
    out_rows: List[Dict[str, Any]] = []
    for row in rows:
        if cap <= 0:
            out_rows.append(row)
            continue
        league = str(row.get("league") or "EPL").upper()
        if not fixture_needs_odds(row):
            out_rows.append(row)
            continue
        cap -= 1
        try:
            fixed = rescue_fixture_odds(aggregator, row, league, enriched=row)
            out_rows.append(fixed)
            if fixed.get("odds_available"):
                rescued += 1
            else:
                still_thin += 1
        except Exception:
            out_rows.append(row)
            still_thin += 1

    report = {
        "rescued": rescued,
        "still_thin": still_thin,
        "attempted": rescued + still_thin,
        "coverage": odds_coverage_summary(out_rows),
        "rows": out_rows,
    }
    return report
