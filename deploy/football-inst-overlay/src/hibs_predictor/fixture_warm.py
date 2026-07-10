"""Headless fixture bundle warm — importable from cron/backfill scripts."""

from __future__ import annotations

import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from dotenv import load_dotenv


def _truthy(name: str, default: str = "0") -> bool:
    load_dotenv()
    return (os.getenv(name, default) or "").strip().lower() in ("1", "true", "yes", "on")


def _app_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _maybe_low_source_backfill(rows: int) -> None:
    if rows > 0:
        return
    try:
        from hibs_predictor.scrape_first import scrape_first_mode

        if not scrape_first_mode():
            return
    except Exception:
        return
    script = _app_root() / "scripts" / "warm_low_source_scrape.sh"
    if not script.is_file():
        return
    subprocess.run(
        ["bash", str(script)],
        cwd=str(_app_root()),
        env={**os.environ, "HOME": str(_app_root()), "DEPLOY_PATH": str(_app_root())},
        timeout=1200,
        check=False,
    )


def warm_fixture_bundle(*, force_refresh: bool = False) -> Dict[str, Any]:
    """Fetch/warm the all-fixtures disk bundle; optionally log prediction snapshots."""
    load_dotenv()
    from hibs_predictor.cache import Cache
    from hibs_predictor.web import (
        _all_fixtures_cache_key,
        _all_fixtures_bundle_fresh,
        _is_complete_fixture_bundle,
        fetch_all_fixtures,
    )

    t0 = time.perf_counter()
    include_domestic = _truthy("HIBS_FETCH_ALL_DOMESTIC")
    force = _truthy("HIBS_FIXTURE_WARM_FORCE")
    if force_refresh:
        force = True
    log_preds = not _truthy("HIBS_FIXTURE_WARM_SKIP_PREDICTIONS")

    cache = Cache()
    ck = _all_fixtures_cache_key(include_domestic=include_domestic)
    peek = cache.peek(ck)

    report: Dict[str, Any] = {
        "status": "ok",
        "at": datetime.now(timezone.utc).isoformat(),
        "cache_key": ck,
        "include_domestic": include_domestic,
        "force": force,
        "force_refresh": force_refresh,
    }

    if (
        not force
        and not force_refresh
        and isinstance(peek, dict)
        and _is_complete_fixture_bundle(peek)
        and _all_fixtures_bundle_fresh(peek)
    ):
        rows = peek.get("all") or []
        n = len(rows)
        report.update(
            {
                "skipped": True,
                "reason": "bundle_fresh_on_disk",
                "count": n,
                "fixture_count": n,
                "elapsed_sec": round(time.perf_counter() - t0, 2),
            }
        )
        return report

    try:
        bundle = fetch_all_fixtures(
            force_refresh=force_refresh or force,
            attach_live=False,
            include_domestic=include_domestic,
            allow_stale=True,
            reboost=_truthy("HIBS_FIXTURE_WARM_REBOOST"),
        )
    except Exception as exc:
        report.update(
            {
                "status": "error",
                "error": str(exc)[:240],
                "elapsed_sec": round(time.perf_counter() - t0, 2),
            }
        )
        return report

    rows = bundle.get("all") or []
    report.update(
        {
            "skipped": False,
            "count": len(rows),
            "fixture_count": len(rows),
            "cache_stale": bool(bundle.get("cache_stale")),
            "cold_start": bool(bundle.get("cold_start")),
            "on_disk": bool(cache.peek(ck)),
            "elapsed_sec": round(time.perf_counter() - t0, 2),
        }
    )

    if log_preds and rows:
        try:
            from hibs_predictor.prediction_log import log_predictions_from_fixtures, prediction_log_enabled

            if prediction_log_enabled():
                report["predictions_logged"] = log_predictions_from_fixtures(rows)
        except Exception as exc:
            report["prediction_log_error"] = str(exc)[:160]

    if not rows:
        _maybe_low_source_backfill(0)
        report["low_source_backfill"] = True
        report["status"] = "empty"

    return report
