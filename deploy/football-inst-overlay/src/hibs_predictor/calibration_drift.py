"""Rolling calibration drift vs baseline Brier cache."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from dotenv import load_dotenv

from hibs_predictor.historic_calibration import calibration_cache_path


def _load_cache() -> Dict[str, Any]:
    path = calibration_cache_path()
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def drift_summary_dict(*, window_days: int = 28) -> Dict[str, Any]:
    """Compare recent audit Brier to calibration_v1 baseline."""
    load_dotenv()
    cache = _load_cache()
    baseline = cache.get("baseline_brier")
    out: Dict[str, Any] = {
        "ok": False,
        "status": "red",
        "window_days": int(window_days),
        "baseline_brier": baseline,
        "rolling_brier": None,
        "drift_pp": None,
        "drift_pass": False,
        "generated_at": cache.get("generated_at"),
        "cache_path": calibration_cache_path(),
    }
    if baseline is None:
        out["message"] = "No calibration cache — run calibration-fit after scored rows."
        return out

    try:
        from hibs_predictor.prediction_log import monitor_summary_dict

        rolling = monitor_summary_dict(days=window_days)
        rb = rolling.get("brier_score_1x2")
        out["rolling_brier"] = rb
        out["n_scored"] = rolling.get("n_scored")
        if rb is None:
            out["message"] = "Insufficient scored rows for drift window."
            out["status"] = "amber"
            return out
        drift = float(rb) - float(baseline)
        out["drift_pp"] = round(drift * 100.0, 2)
        # Institutional: alert when rolling Brier worse than baseline by >3pp
        out["drift_pass"] = drift <= 0.03
        out["ok"] = True
        if drift <= 0.0:
            out["status"] = "green"
        elif drift <= 0.03:
            out["status"] = "amber"
        else:
            out["status"] = "red"
            out["message"] = f"Rolling Brier {rb:.3f} vs baseline {baseline:.3f} (+{out['drift_pp']}pp)"
    except Exception as exc:
        out["error"] = str(exc)[:120]
        out["message"] = str(exc)[:120]
    out["checked_at"] = datetime.now(timezone.utc).isoformat()
    return out
