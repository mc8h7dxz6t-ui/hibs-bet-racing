"""Inst++ unified racing scrape cycle — cards, odds, thin rescue, telemetry."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from hibs_racing.scrapers.racing_scrape_api import (
    odds_coverage_summary,
    resolve_cards_source,
    run_thin_rescue_pass,
)
from hibs_racing.scrapers.scrape_resilience import scrape_resilience_status


def _log_dir() -> Path:
    return Path(os.getenv("LOG_DIR", "logs"))


def _status_path() -> Path:
    custom = os.getenv("HIBS_RACING_ROBUST_SCRAPE_STATUS")
    if custom:
        return Path(custom)
    return _log_dir() / "robust-racing-scrape.json"


def read_robust_scrape_status() -> Dict[str, Any]:
    path = _status_path()
    if not path.is_file():
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
    *,
    force: bool = False,
    window_hours: int = 48,
    odds_source: str = "auto",
) -> Dict[str, Any]:
    """Headless refresh + optional thin rescue; cron-safe."""
    from hibs_racing.cards.refresh import refresh_cards
    from hibs_racing.scrape_first import scrape_first_status

    t0 = datetime.now(timezone.utc)
    source = resolve_cards_source()
    report: Dict[str, Any] = {
        "ok": False,
        "at": t0.isoformat(),
        "mode": "robust_racing_scrape_cycle",
        "scrape_first": scrape_first_status(),
        "cards_source": source,
        "force": force,
    }
    try:
        stats = refresh_cards(
            source=source,
            odds_source=odds_source,
            window_hours=window_hours,
            regions=("gb", "ire"),
        )
        report["refresh"] = stats
        report["runner_count"] = stats.get("runners", 0)
        report["race_count"] = stats.get("races", 0)
        report["odds_source"] = stats.get("odds_source")
        report["odds_runners"] = stats.get("odds_runners", 0)
        report["ok"] = int(stats.get("runners") or 0) > 0
    except Exception as exc:
        report["error"] = str(exc)[:200]
        if source == "racing_api":
            from hibs_racing.racing_api_guard import record_forbidden

            record_forbidden(http_status=403, reason=str(exc)[:80])
            fallback = resolve_cards_source("rpscrape")
            if fallback != source:
                try:
                    stats = refresh_cards(
                        source=fallback,
                        odds_source=odds_source,
                        window_hours=window_hours,
                        regions=("gb", "ire"),
                    )
                    report["refresh"] = stats
                    report["cards_source"] = fallback
                    report["fallback_used"] = True
                    report["runner_count"] = stats.get("runners", 0)
                    report["ok"] = int(stats.get("runners") or 0) > 0
                except Exception as exc2:
                    report["fallback_error"] = str(exc2)[:200]

    if os.getenv("HIBS_RACING_ROBUST_RESCUE", "1").strip().lower() in ("1", "true", "yes", "on"):
        try:
            rescue = run_thin_rescue_pass()
            report["thin_rescue"] = rescue
            cov = rescue.get("coverage") or odds_coverage_summary()
            report["odds_coverage_pct"] = cov.get("coverage_pct")
            report["priced_runners"] = cov.get("priced")
        except Exception as exc:
            report["thin_rescue_error"] = str(exc)[:120]

    report["resilience"] = scrape_resilience_status()
    elapsed = (datetime.now(timezone.utc) - t0).total_seconds()
    report["elapsed_sec"] = round(elapsed, 2)
    write_robust_scrape_status(report)
    return report


def robust_scrape_slo_status() -> Dict[str, Any]:
    report = read_robust_scrape_status()
    cov = odds_coverage_summary()
    max_age_h = float(os.getenv("HIBS_RACING_ROBUST_SCRAPE_MAX_AGE_HOURS", "3"))
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
    runners = int(report.get("runner_count") or cov.get("total") or 0)
    odds_pct = report.get("odds_coverage_pct") or cov.get("coverage_pct")
    min_odds = float(os.getenv("HIBS_RACING_ODDS_COVERAGE_MIN_PCT", "40"))
    priced = int(report.get("priced_runners") or cov.get("priced") or 0)
    odds_ok = priced > 0 or odds_pct is None or float(odds_pct) >= min_odds
    ok = runners > 0 and (fresh or not report.get("at")) and odds_ok
    return {
        "ok": ok,
        "report_fresh": fresh,
        "report_age_hours": age_h,
        "max_age_hours": max_age_h,
        "runner_count": runners,
        "odds_coverage_pct": odds_pct,
        "priced_runners": priced,
        "resilience_ok": (report.get("resilience") or {}).get("ledger", {}).get("ok", True),
        "message": "ok" if ok else ("stale_report" if report.get("at") and not fresh else "thin_cards_or_odds"),
    }
