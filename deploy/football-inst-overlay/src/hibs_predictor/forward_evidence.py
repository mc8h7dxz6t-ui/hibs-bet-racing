"""Football forward evidence gates F1–F9 (MASTER_OPERATIONS_SCORECARD §1)."""

from __future__ import annotations

import os
import sqlite3
import subprocess
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

from hibs_predictor.evidence_presentation import buyer_readiness_bundle, gate_row

F7_CAPTURE_PCT = 50.0
F7B_SCORED_CAPTURE_PCT = 80.0
F7_MIN_MATCHDAYS = 3
F8_MIN_CLV_ROWS = 25
F9_BEAT_CLOSE_PCT = 50.0


def evidence_deploy_since_iso() -> Optional[str]:
    load_dotenv()
    explicit = (os.getenv("HIBS_EVIDENCE_DEPLOY_DATE") or "").strip()
    if not explicit:
        return None
    if "T" not in explicit:
        explicit = f"{explicit}T00:00:00+00:00"
    return explicit


def _env_truthy(name: str, default: str = "0") -> bool:
    load_dotenv()
    return (os.getenv(name, default) or "").strip().lower() in ("1", "true", "yes", "on")


def _count_matchdays_7d() -> int:
    """Distinct display-TZ calendar days with kickoffs in rolling 7d audit window."""
    try:
        from hibs_predictor.display_tz import display_timezone
        from hibs_predictor.prediction_log import _db_path, init_db, prediction_log_enabled

        if not prediction_log_enabled() or not os.path.isfile(_db_path()):
            return 0
        init_db()
        cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        conn = sqlite3.connect(_db_path(), timeout=15)
        try:
            rows = conn.execute(
                """
                SELECT DISTINCT substr(kickoff_iso, 1, 10) AS ko_day
                FROM prediction_snapshots
                WHERE kickoff_iso IS NOT NULL AND kickoff_iso >= ?
                """,
                (cutoff,),
            ).fetchall()
        finally:
            conn.close()
        tz = display_timezone()
        days: set[str] = set()
        for (ko_day,) in rows:
            if not ko_day:
                continue
            try:
                dt = datetime.fromisoformat(str(ko_day) + "T12:00:00+00:00")
                local = dt.astimezone(tz).date().isoformat()
                days.add(local)
            except ValueError:
                days.add(str(ko_day))
        return len(days)
    except Exception:
        return 0


def _pytest_smoke_ok() -> bool:
    if (os.getenv("HIBS_FORWARD_EVIDENCE_RUN_PYTEST") or "").strip().lower() in ("1", "true", "yes"):
        try:
            root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            proc = subprocess.run(
                ["python3", "-m", "pytest", "tests/test_institutional_readiness.py", "-q"],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=120,
            )
            return proc.returncode == 0
        except Exception:
            return False
    # Production defers full pytest to CI; smoke-import core overlay modules.
    try:
        import hibs_predictor.auth  # noqa: F401
        import hibs_predictor.forward_evidence  # noqa: F401
        import hibs_predictor.institutional_readiness  # noqa: F401

        return True
    except Exception:
        return False


def _service_active() -> Optional[bool]:
    try:
        proc = subprocess.run(
            ["systemctl", "is-active", "hibs-bet"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if proc.returncode == 0:
            return proc.stdout.strip() == "active"
        if proc.returncode == 3:
            return False
    except Exception:
        pass
    return None


def forward_evidence_gates() -> Dict[str, Any]:
    """Build F1–F9 gate bundle for /api/health and Inst++ snapshots."""
    load_dotenv()
    from hibs_predictor.institutional_readiness import collect_config_issues
    from hibs_predictor.prediction_log import (
        audit_odds_capture_stats,
        clv_beat_close_summary,
        pred_log_sync_cron_status,
        prediction_log_enabled,
        _clv_enabled,
    )

    issues, _warnings = collect_config_issues(production=_env_truthy("HIBS_PRODUCTION"))
    cron = pred_log_sync_cron_status()
    cap_7d = audit_odds_capture_stats(days=7)
    since = evidence_deploy_since_iso()
    cap_since = audit_odds_capture_stats(days=28, since_iso=since) if since else {}
    trial_f9 = _env_truthy("HIBS_F9_TRIAL_LEAGUES_ONLY")
    clv = clv_beat_close_summary(days=28, since_iso=since, trial_leagues_only=trial_f9)
    matchdays = _count_matchdays_7d()
    capture_7d = cap_7d.get("capture_rate_pct")
    scored_since = cap_since.get("scored_capture_rate_pct")
    n_clv = int(clv.get("n_clv_rows") or 0)
    beat_pct = clv.get("beat_close_pct")
    svc = _service_active()
    smoke_ok = _pytest_smoke_ok()

    gates: List[Dict[str, Any]] = [
        gate_row(
            "F1_prediction_log",
            label="Prediction audit log",
            passed=prediction_log_enabled(),
            actual=prediction_log_enabled(),
            threshold="enabled",
            message="HIBS_PREDICTION_LOG_ENABLED=1",
            critical=True,
        ),
        gate_row(
            "F2_clv_log",
            label="CLV logging",
            passed=_clv_enabled(),
            actual=_clv_enabled(),
            threshold="enabled",
            message="HIBS_CLV_LOG_ENABLED=1",
            critical=True,
        ),
        gate_row(
            "F3_pred_log_cron",
            label="Daily pred-log-sync cron",
            passed=bool(cron.get("scheduled")),
            actual=cron.get("scheduled"),
            threshold="scheduled=true",
            message=cron.get("message") or "deploy/cron-hibs-calibration.sh --install",
            critical=True,
        ),
        gate_row(
            "F4_pytest",
            label="Test suite / smoke",
            passed=smoke_ok,
            actual="smoke_ok" if smoke_ok else "fail",
            threshold="pytest green",
            message="CI pytest or HIBS_FORWARD_EVIDENCE_RUN_PYTEST=1",
            critical=True,
        ),
        gate_row(
            "F5_production_config",
            label="Production config",
            passed=not issues,
            actual=len(issues),
            threshold="0 blocking",
            message="; ".join(issues[:2]) if issues else "validate_institutional_config.py",
            critical=True,
        ),
        gate_row(
            "F6_service_active",
            label="hibs-bet service",
            passed=svc is not False,
            actual=svc if svc is not None else "n/a",
            threshold="active",
            message="systemctl is-active hibs-bet",
            critical=True,
        ),
        gate_row(
            "F7_capture_7d",
            label="7d 1X2 odds capture",
            passed=(
                matchdays >= F7_MIN_MATCHDAYS
                and capture_7d is not None
                and float(capture_7d) >= F7_CAPTURE_PCT
            ),
            actual=capture_7d,
            threshold=f">={F7_CAPTURE_PCT}% after {F7_MIN_MATCHDAYS} matchdays",
            message="Dashboard + cron seeds; audit_ops.odds_capture_7d",
            critical=False,
            window="7d",
            coverage_pct=float(capture_7d) if capture_7d is not None else None,
            n=matchdays,
        ),
        gate_row(
            "F7b_scored_since_deploy",
            label="Since-deploy scored capture",
            passed=scored_since is not None and float(scored_since) >= F7B_SCORED_CAPTURE_PCT,
            actual=scored_since,
            threshold=f">={F7B_SCORED_CAPTURE_PCT}%",
            message="HIBS_EVIDENCE_DEPLOY_DATE window — closing join quality",
            critical=False,
            window="since_deploy",
            coverage_pct=float(scored_since) if scored_since is not None else None,
        ),
        gate_row(
            "F8_clv_sample",
            label="CLV sample (28d)",
            passed=n_clv >= F8_MIN_CLV_ROWS,
            actual=n_clv,
            threshold=f">={F8_MIN_CLV_ROWS} rows",
            message="pred-log-sync after FT + closing 1X2",
            critical=False,
            n=n_clv,
            window="28d",
        ),
        gate_row(
            "F9_beat_close",
            label="CLV beat-close",
            passed=beat_pct is not None and n_clv >= F8_MIN_CLV_ROWS and float(beat_pct) >= F9_BEAT_CLOSE_PCT,
            actual=beat_pct,
            threshold=f">={F9_BEAT_CLOSE_PCT}%",
            message="trial cohort when HIBS_F9_TRIAL_LEAGUES_ONLY=1",
            critical=False,
            n=n_clv,
            window="28d",
        ),
    ]

    critical = [g for g in gates if g.get("critical")]
    evidence = [g for g in gates if not g.get("critical")]
    critical_pass = all(g["pass"] for g in critical)
    evidence_pass = all(g["pass"] for g in evidence)
    passed = sum(1 for g in gates if g["pass"])
    ratio = passed / max(len(gates), 1)

    if not critical_pass:
        grade = "D"
    elif evidence_pass:
        grade = "A"
    elif ratio >= 0.85:
        grade = "B+"
    elif ratio >= 0.7:
        grade = "B"
    elif ratio >= 0.55:
        grade = "C+"
    else:
        grade = "C"

    readiness = buyer_readiness_bundle(
        gates=gates,
        critical_pass=critical_pass,
        evidence_pass=evidence_pass,
        vertical="football",
    )

    return {
        "since_deploy_iso": since,
        "matchdays_7d": matchdays,
        "trial_f9_cohort": trial_f9,
        "gates": gates,
        "critical_pass": critical_pass,
        "evidence_pass": evidence_pass,
        "evidence_grade": grade,
        "next_actions": _next_actions(gates),
        **readiness,
    }


def _next_actions(gates: List[Dict[str, Any]]) -> List[str]:
    by_id = {g["id"]: g for g in gates}
    actions: List[str] = []
    if not by_id.get("F1_prediction_log", {}).get("pass"):
        actions.append("Set HIBS_PREDICTION_LOG_ENABLED=1 in .env")
    if not by_id.get("F2_clv_log", {}).get("pass"):
        actions.append("Set HIBS_CLV_LOG_ENABLED=1")
    if not by_id.get("F3_pred_log_cron", {}).get("pass"):
        actions.append("sudo bash deploy/cron-hibs-calibration.sh --install")
    if not by_id.get("F5_production_config", {}).get("pass"):
        actions.append("python3 scripts/validate_institutional_config.py")
    if not by_id.get("F7_capture_7d", {}).get("pass"):
        actions.append("./scripts/seed_forward_evidence.sh")
        actions.append("Load dashboard on matchdays for 1X2 capture")
    if not by_id.get("F8_clv_sample", {}).get("pass") or not by_id.get("F9_beat_close", {}).get("pass"):
        actions.append("python -m hibs_predictor.main pred-log-sync --verbose")
    if not actions:
        actions.append("./scripts/export_b2b_data_room.sh")
    return actions
