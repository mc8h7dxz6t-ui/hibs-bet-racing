"""Failsafe wrappers — health never 500s on evidence DB errors."""

from __future__ import annotations

import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from dotenv import load_dotenv


def safe_forward_evidence_gates() -> Dict[str, Any]:
    """L2 evidence gates with broad exception guard."""
    try:
        from hibs_predictor.forward_evidence import forward_evidence_gates

        return forward_evidence_gates()
    except Exception as exc:
        return {
            "buyer_ready": False,
            "critical_pass": False,
            "evidence_pass": False,
            "evidence_grade": "D",
            "gates": [],
            "error": str(exc)[:160],
            "failsafe": True,
        }


def failsafe_report(*, app_root: str | None = None) -> Dict[str, Any]:
    """Aggregate engineering + automation failsafe snapshot."""
    load_dotenv()
    root = Path(app_root or os.getenv("DEPLOY_PATH", "/opt/hibs-bet"))
    out: Dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "app_root": str(root),
        "failsafe_ok": False,
    }
    try:
        from hibs_predictor.institutional_readiness import collect_config_issues, readiness_dict

        ir = readiness_dict()
        issues, warnings = collect_config_issues(production=True)
        out["engineering_grade"] = ir.get("engineering_grade")
        out["evidence_grade"] = ir.get("evidence_grade")
        out["blocking_issues"] = issues
        out["warnings"] = warnings
        out["engineering_ok"] = not issues
    except Exception as exc:
        out["readiness_error"] = str(exc)[:120]

    try:
        fwd = safe_forward_evidence_gates()
        out["buyer_ready_football"] = bool(fwd.get("buyer_ready"))
        out["forward_critical_pass"] = bool(fwd.get("critical_pass"))
    except Exception as exc:
        out["forward_error"] = str(exc)[:120]

    try:
        from hibs_predictor.prediction_log import pred_log_sync_cron_status

        cron = pred_log_sync_cron_status()
        out["pred_log_cron_scheduled"] = bool(cron.get("scheduled"))
    except Exception as exc:
        out["cron_error"] = str(exc)[:120]

    try:
        proc = subprocess.run(
            ["systemctl", "is-active", "hibs-bet"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        out["hibs_bet_active"] = proc.stdout.strip() == "active"
    except Exception:
        out["hibs_bet_active"] = None

    out["failsafe_ok"] = bool(
        out.get("engineering_ok")
        and out.get("forward_critical_pass")
        and out.get("pred_log_cron_scheduled") is not False
        and out.get("hibs_bet_active") is not False
    )
    return out
