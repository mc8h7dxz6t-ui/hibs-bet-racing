#!/usr/bin/env python3
"""Headless football fixture bundle warm — runs outside gunicorn (cron/systemd).

Skips when disk bundle is complete and fresh unless HIBS_FIXTURE_WARM_FORCE=1.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")


def _truthy(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


def main() -> int:
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
    force_refresh = _truthy("HIBS_FIXTURE_WARM_FORCE_REFRESH")
    log_preds = not _truthy("HIBS_FIXTURE_WARM_SKIP_PREDICTIONS")

    cache = Cache()
    ck = _all_fixtures_cache_key(include_domestic=include_domestic)
    peek = cache.peek(ck)

    report: dict = {
        "ok": True,
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
        n = len(peek.get("all") or [])
        report.update(
            {
                "skipped": True,
                "reason": "bundle_fresh_on_disk",
                "count": n,
                "elapsed_sec": round(time.perf_counter() - t0, 2),
            }
        )
        print(json.dumps(report))
        return 0

    try:
        bundle = fetch_all_fixtures(
            force_refresh=force_refresh,
            attach_live=False,
            include_domestic=include_domestic,
            allow_stale=True,
            reboost=_truthy("HIBS_FIXTURE_WARM_REBOOST"),
        )
    except Exception as exc:
        report.update({"ok": False, "error": str(exc)[:240], "elapsed_sec": round(time.perf_counter() - t0, 2)})
        print(json.dumps(report))
        return 1

    rows = bundle.get("all") or []
    report.update(
        {
            "skipped": False,
            "count": len(rows),
            "cache_stale": bool(bundle.get("cache_stale")),
            "cold_start": bool(bundle.get("cold_start")),
            "on_disk": bool(cache.peek(ck)),
            "elapsed_sec": round(time.perf_counter() - t0, 2),
        }
    )

    logged = 0
    if log_preds and rows:
        try:
            from hibs_predictor.prediction_log import log_predictions_from_fixtures, prediction_log_enabled

            if prediction_log_enabled():
                logged = log_predictions_from_fixtures(rows)
                report["predictions_logged"] = logged
        except Exception as exc:
            report["prediction_log_error"] = str(exc)[:160]

    print(json.dumps(report))
    return 0 if rows else 2


if __name__ == "__main__":
    raise SystemExit(main())
