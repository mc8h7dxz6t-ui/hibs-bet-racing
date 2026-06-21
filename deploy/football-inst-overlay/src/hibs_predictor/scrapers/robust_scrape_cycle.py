"""Inst++ unified robust scrape cycle — fixtures, enrich, odds rescue, telemetry."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from hibs_predictor.scrapers.low_source_api import run_low_source_scrape_cycle


def _log_dir() -> Path:
    return Path(os.getenv("LOG_DIR", "/var/log/hibs-bet"))


def _status_path() -> Path:
    return _log_dir() / "robust-scrape.json"


def read_robust_scrape_status() -> Dict[str, Any]:
    path = _status_path()
    if not path.is_file():
        low = _log_dir() / "low-source-scrape.json"
        if low.is_file():
            try:
                return json.loads(low.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                pass
        return {"ok": False, "message": "no_report"}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"ok": False, "message": "invalid_report"}
    except (OSError, json.JSONDecodeError):
        return {"ok": False, "message": "read_error"}


def write_robust_scrape_status(report: Dict[str, Any]) -> None:
    path = _status_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass


def run_robust_scrape_cycle(
    aggregator: Any,
    *,
    include_domestic: bool = False,
    force: bool = False,
) -> Dict[str, Any]:
    """Full scrape-first cycle with odds rescue and resilience telemetry."""
    t0 = datetime.now(timezone.utc)
    fixture_report = run_low_source_scrape_cycle(
        aggregator,
        include_domestic=include_domestic,
        force=force,
    )
    elapsed = (datetime.now(timezone.utc) - t0).total_seconds()
    report: Dict[str, Any] = {
        "ok": bool(fixture_report.get("ok")),
        "at": t0.isoformat(),
        "mode": "robust_scrape_cycle",
        "elapsed_sec": round(elapsed, 2),
        **fixture_report,
    }
    write_robust_scrape_status(report)
    return report


def robust_scrape_slo_status() -> Dict[str, Any]:
    """SLO probe for automation — reads last cycle report + bundle odds coverage."""
    from hibs_predictor.data_producer_slo import football_fixture_bundle_status

    report = read_robust_scrape_status()
    bundle = football_fixture_bundle_status()
    max_age_h = float(os.getenv("HIBS_ROBUST_SCRAPE_MAX_AGE_HOURS", "3"))
    age_h: Optional[float] = None
    raw_at = report.get("at")
    if raw_at:
        try:
            at = datetime.fromisoformat(str(raw_at))
            if at.tzinfo is None:
                at = at.replace(tzinfo=timezone.utc)
            age_h = round((datetime.now(timezone.utc) - at).total_seconds() / 3600.0, 2)
        except (TypeError, ValueError):
            pass
    fresh = age_h is not None and age_h <= max_age_h
    fixtures_ok = int(report.get("fixture_count") or 0) > 0 or int(bundle.get("fixture_count") or 0) > 0
    odds_pct = report.get("odds_coverage_pct")
    if odds_pct is None:
        odds_pct = bundle.get("odds_coverage_pct")
    min_odds = float(os.getenv("HIBS_ODDS_COVERAGE_MIN_PCT", "40"))
    with_odds = int(report.get("with_1x2_odds") or bundle.get("with_1x2_odds") or 0)
    odds_ok = with_odds > 0 or odds_pct is None or float(odds_pct) >= min_odds
    ok = fixtures_ok and (fresh or not report.get("at")) and odds_ok
    return {
        "ok": ok,
        "report_fresh": fresh,
        "report_age_hours": age_h,
        "max_age_hours": max_age_h,
        "fixture_count": report.get("fixture_count") or bundle.get("fixture_count"),
        "odds_coverage_pct": odds_pct,
        "bundle_odds_coverage_pct": bundle.get("odds_coverage_pct"),
        "with_1x2_odds": with_odds,
        "resilience_ok": (report.get("resilience") or {}).get("ledger", {}).get("ok", True),
        "message": "ok" if ok else ("stale_report" if report.get("at") and not fresh else "thin_odds_or_fixtures"),
    }
