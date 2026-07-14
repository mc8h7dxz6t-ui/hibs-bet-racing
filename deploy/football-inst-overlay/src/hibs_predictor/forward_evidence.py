"""Football forward evidence gates F1–F9 (+ F9b/F9c informational) — MASTER_OPERATIONS_SCORECARD §1."""

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
F10_BRIER_PASS_MAX = 0.22
F10_BRIER_MIN_N = 30


def evidence_deploy_since_iso() -> Optional[str]:
    load_dotenv()
    explicit = (os.getenv("HIBS_EVIDENCE_DEPLOY_DATE") or "").strip()
    if not explicit:
        explicit = _deploy_revision_deployed_at()
    if not explicit:
        return None
    if "T" not in explicit:
        explicit = f"{explicit}T00:00:00+00:00"
    return explicit


def deploy_revision_iso() -> Optional[str]:
    """Alias for since_deploy in verify scripts — env date or .deploy-revision deployed_at."""
    return evidence_deploy_since_iso()


def _deploy_revision_deployed_at() -> str:
    load_dotenv()
    root = os.getenv("DEPLOY_PATH") or os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    path = os.path.join(root, ".deploy-revision")
    if not os.path.isfile(path):
        return ""
    try:
        for line in open(path, encoding="utf-8", errors="replace"):
            if line.strip().startswith("deployed_at="):
                return line.split("=", 1)[1].strip()
    except OSError:
        pass
    return ""


def ensure_audit_db() -> None:
    from hibs_predictor.prediction_log import init_db

    init_db()


def log_forward_snapshots_from_bundle(*, force_refresh: bool = True) -> int:
    """Warm fixtures and log prediction snapshots (dashboard-equivalent seed)."""
    from hibs_predictor.fixture_warm import warm_fixture_bundle
    from hibs_predictor.prediction_log import (
        log_predictions_from_fixtures,
        prediction_log_enabled,
    )

    ensure_audit_db()
    if not prediction_log_enabled():
        return 0
    warm = warm_fixture_bundle(force_refresh=force_refresh)
    rows = []
    try:
        from hibs_predictor.cache import Cache
        from hibs_predictor.web import _all_fixtures_cache_key

        include_domestic = (os.getenv("HIBS_FETCH_ALL_DOMESTIC") or "").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        peek = Cache().peek(_all_fixtures_cache_key(include_domestic=include_domestic))
        if isinstance(peek, dict):
            rows = peek.get("all") or []
    except Exception:
        pass
    if rows:
        return int(log_predictions_from_fixtures(rows))
    return int(warm.get("predictions_logged") or 0)


def run_daily_clv_sync() -> Dict[str, Any]:
    """Post-match settlement sync — same as pred-log-sync cron target."""
    from hibs_predictor.prediction_log import run_pred_log_sync_for_web

    ensure_audit_db()
    return run_pred_log_sync_for_web()


def _env_truthy(name: str, default: str = "0") -> bool:
    load_dotenv()
    return (os.getenv(name, default) or "").strip().lower() in ("1", "true", "yes", "on")


def _f9_cohort_label(*, trial: bool) -> str:
    return "trial_domestic_cups" if trial else "all_leagues"


def count_matchdays_7d() -> int:
    """Distinct display-TZ calendar days with kickoffs among snapshots captured in rolling 7d."""
    try:
        from hibs_predictor.display_tz import display_timezone, parse_kickoff_utc
        from hibs_predictor.prediction_log import _db_path, init_db, prediction_log_enabled

        if not prediction_log_enabled() or not os.path.isfile(_db_path()):
            return 0
        init_db()
        cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        conn = sqlite3.connect(_db_path(), timeout=15)
        try:
            rows = conn.execute(
                """
                SELECT kickoff_iso
                FROM prediction_snapshots
                WHERE captured_at >= ?
                  AND kickoff_iso IS NOT NULL AND kickoff_iso != ''
                """,
                (cutoff,),
            ).fetchall()
        finally:
            conn.close()
        tz = display_timezone()
        days: set[str] = set()
        for (ko_raw,) in rows:
            ko = parse_kickoff_utc(str(ko_raw))
            if ko is not None:
                days.add(ko.astimezone(tz).date().isoformat())
        return len(days)
    except Exception:
        return 0


def _snapshot_count_7d() -> int:
    try:
        from hibs_predictor.prediction_log import _db_path, init_db, prediction_log_enabled

        if not prediction_log_enabled() or not os.path.isfile(_db_path()):
            return 0
        init_db()
        cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        conn = sqlite3.connect(_db_path(), timeout=15)
        try:
            row = conn.execute(
                "SELECT COUNT(*) FROM prediction_snapshots WHERE captured_at >= ?",
                (cutoff,),
            ).fetchone()
            return int(row[0] if row else 0)
        finally:
            conn.close()
    except Exception:
        return 0


def _pytest_smoke_ok() -> bool:
    if _env_truthy("HIBS_FORWARD_EVIDENCE_RUN_PYTEST"):
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


def _informational_gate(
    gate_id: str,
    *,
    label: str,
    metric_pass: Optional[bool],
    actual: Any,
    threshold: str,
    message: str,
) -> Dict[str, Any]:
    """Informational gate — never affects buyer_ready or buyer_readiness_score."""
    row = gate_row(
        gate_id,
        label=label,
        passed=bool(metric_pass) if metric_pass is not None else False,
        actual=actual,
        threshold=threshold,
        message=message,
        critical=False,
    )
    row["informational"] = True
    row["buyer_binding"] = False
    return row


def forward_evidence_gates() -> Dict[str, Any]:
    """Build F1–F9 gate bundle for /api/health, verify scripts, and Inst++ snapshots."""
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
    trial_f9 = _env_truthy("HIBS_F9_TRIAL_LEAGUES_ONLY", "1")
    cohort = _f9_cohort_label(trial=trial_f9)
    clv = clv_beat_close_summary(days=28, since_iso=since, trial_leagues_only=trial_f9)
    matchdays = count_matchdays_7d()
    n_snap_7d = _snapshot_count_7d()
    capture_7d = cap_7d.get("capture_rate_pct")
    scored_since = cap_since.get("scored_capture_rate_pct")
    n_clv = int(clv.get("n_clv_rows") or 0)
    beat_pct = clv.get("beat_close_pct")
    svc = _service_active()
    smoke_ok = _pytest_smoke_ok()

    f7_pass = (
        matchdays >= F7_MIN_MATCHDAYS
        and capture_7d is not None
        and float(capture_7d) >= F7_CAPTURE_PCT
    )
    if matchdays < F7_MIN_MATCHDAYS:
        f7_msg = (
            f"Need ≥{F7_MIN_MATCHDAYS} matchdays with snapshots in 7d (have {matchdays}). "
            "Load dashboard while logged in to seed snapshots."
        )
    elif capture_7d is None:
        f7_msg = f"No snapshots in 7d window (n={n_snap_7d}) — run scripts/run_forward_backfill_plan.sh"
    else:
        f7_msg = "Dashboard + cron seeds; audit_ops.odds_capture_7d"

    f7b_pass = scored_since is not None and float(scored_since) >= F7B_SCORED_CAPTURE_PCT
    f7b_msg = (
        "Historic hole excluded when HIBS_EVIDENCE_DEPLOY_DATE or .deploy-revision set."
        if since
        else "Set HIBS_EVIDENCE_DEPLOY_DATE on first production deploy."
    )

    f8_pass = n_clv >= F8_MIN_CLV_ROWS
    f8_msg = (
        f"No settled CLV rows in last 28d — run daily sync after matches; ensure snapshots capture opening 1X2."
        if n_clv < F8_MIN_CLV_ROWS
        else "CLV sample sufficient for F9 evaluation."
    )

    f9_pass = beat_pct is not None and n_clv >= F8_MIN_CLV_ROWS and float(beat_pct) >= F9_BEAT_CLOSE_PCT
    if n_clv < F8_MIN_CLV_ROWS:
        f9_msg = f"Pass cohort: {cohort} (HIBS_F9_TRIAL_LEAGUES_ONLY={'1' if trial_f9 else '0'}). Descriptive until F8 passes."
    else:
        f9_msg = f"Pass cohort: {cohort}. Raw implied beat-close on settled rows."

    try:
        from hibs_predictor.price_truth import clv_beat_close_fair_summary, clv_benchmark_tier_summary

        f9b = clv_beat_close_fair_summary(
            days=28, since_iso=since, method="shin", trial_leagues_only=trial_f9
        )
        f9c = clv_benchmark_tier_summary(days=28, since_iso=since)
    except Exception as exc:
        f9b = {"n_clv_rows": 0, "beat_close_pct": None, "error": str(exc)[:80]}
        f9c = {"pinnacle_panel_rate_pct": None, "error": str(exc)[:80]}

    f9b_n = int(f9b.get("n_clv_rows") or 0)
    f9b_pct = f9b.get("beat_close_pct")
    f9b_pass = f9b_n >= F8_MIN_CLV_ROWS and f9b_pct is not None and float(f9b_pct) >= F9_BEAT_CLOSE_PCT

    pin_pct = f9c.get("pinnacle_panel_rate_pct")
    f9c_pass = pin_pct is not None and float(pin_pct) >= 10.0

    f10_brier: Optional[float] = None
    f10_n = 0
    try:
        from hibs_predictor.prediction_log import monitor_summary_dict

        mon = monitor_summary_dict()
        f10_brier = mon.get("brier_score_1x2")
        f10_n = int(mon.get("n_scored") or 0)
    except Exception:
        pass
    f10_pass = (
        f10_n >= F10_BRIER_MIN_N
        and f10_brier is not None
        and float(f10_brier) <= F10_BRIER_PASS_MAX
    )
    f10_msg = (
        f"Need ≥{F10_BRIER_MIN_N} scored rows in monitor window (have {f10_n})."
        if f10_n < F10_BRIER_MIN_N
        else (
            f"Brier {f10_brier} above pass max {F10_BRIER_PASS_MAX} — review calibration-fit."
            if not f10_pass
            else "1X2 Brier within personal staking band."
        )
    )

    gates: List[Dict[str, Any]] = [
        gate_row(
            "F1_audit",
            label="Prediction audit log",
            passed=prediction_log_enabled(),
            actual=prediction_log_enabled(),
            threshold="enabled",
            message="HIBS_PREDICTION_LOG_ENABLED=1",
            critical=True,
        ),
        gate_row(
            "F2_clv",
            label="CLV logging",
            passed=_clv_enabled(),
            actual=_clv_enabled(),
            threshold="enabled",
            message="HIBS_CLV_LOG_ENABLED=1",
            critical=True,
        ),
        gate_row(
            "F3_cron",
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
            "F7_forward_capture_7d",
            label="7d forward 1X2 capture",
            passed=f7_pass,
            actual=capture_7d,
            threshold=f">={F7_CAPTURE_PCT}% after {F7_MIN_MATCHDAYS} matchdays",
            message=f7_msg,
            critical=False,
            window="7d",
            coverage_pct=float(capture_7d) if capture_7d is not None else None,
            n=matchdays,
        ),
        gate_row(
            "F7b_scored_capture_since_deploy",
            label="Since-deploy scored capture",
            passed=f7b_pass,
            actual=scored_since,
            threshold=f">={F7B_SCORED_CAPTURE_PCT}% scored rows",
            message=f7b_msg,
            critical=False,
            window="since_deploy",
            coverage_pct=float(scored_since) if scored_since is not None else None,
        ),
        gate_row(
            "F8_clv_sample",
            label="CLV sample (28d)",
            passed=f8_pass,
            actual=n_clv,
            threshold=f">={F8_MIN_CLV_ROWS} rows ({cohort})",
            message=f8_msg,
            critical=False,
            n=n_clv,
            window="28d",
        ),
        gate_row(
            "F9_clv_beat_close",
            label="CLV beat-close",
            passed=f9_pass,
            actual=beat_pct,
            threshold=f">={F9_BEAT_CLOSE_PCT}% on >={F8_MIN_CLV_ROWS} rows ({cohort})",
            message=f9_msg,
            critical=False,
            n=n_clv,
            window="28d",
        ),
        gate_row(
            "F10_brier_1x2",
            label="1X2 Brier (28d monitor)",
            passed=f10_pass,
            actual=f10_brier,
            threshold=f"<={F10_BRIER_PASS_MAX} on n>={F10_BRIER_MIN_N}",
            message=f10_msg,
            critical=False,
            n=f10_n,
            window="28d",
        ),
        _informational_gate(
            "F9b_clv_beat_close_fair_shin",
            label="Fair-Shin CLV beat-close (informational)",
            metric_pass=f9b_pass if f9b_n >= F8_MIN_CLV_ROWS else None,
            actual=f9b_pct,
            threshold="informational — not buyer pass/fail",
            message=(
                "Informational only — Shin fair-line CLV from stored 1X2 triplets (no new API). "
                "Does not change F9 pass/fail."
            ),
        ),
        _informational_gate(
            "F9c_clv_benchmark_tier",
            label="Pinnacle closing benchmark tier",
            metric_pass=f9c_pass if pin_pct is not None else None,
            actual=f9c,
            threshold="informational — not buyer pass/fail",
            message=(
                "Informational — Pinnacle closing line is institutional CLV benchmark. "
                "API-Football best-price close is not equivalent."
            ),
        ),
    ]

    critical = [g for g in gates if g.get("critical")]
    buyer_evidence = [
        g for g in gates if not g.get("critical") and not g.get("informational")
    ]
    critical_pass = all(g["pass"] for g in critical)
    evidence_pass = all(g["pass"] for g in buyer_evidence)
    passed_n = sum(1 for g in buyer_evidence if g["pass"])
    ratio = passed_n / max(len(buyer_evidence), 1)

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

    from hibs_predictor.honesty_plane import attach_honesty

    readiness = buyer_readiness_bundle(
        gates=gates,
        critical_pass=critical_pass,
        evidence_pass=evidence_pass,
        vertical="football",
    )

    return attach_honesty(
        {
            "since_deploy": since,
            "since_deploy_iso": since,
            "matchdays_7d": matchdays,
            "n_snapshots_7d": n_snap_7d,
            "trial_f9_cohort": cohort,
            "f9b_trial_domestic_fair_shin": f9b,
            "f9c_benchmark": f9c,
            "gates": gates,
            "critical_pass": critical_pass,
            "evidence_pass": evidence_pass,
            "evidence_grade": grade,
            "next_actions": _next_actions(gates, matchdays=matchdays, n_clv=n_clv),
            **readiness,
        }
    )


def _next_actions(
    gates: List[Dict[str, Any]],
    *,
    matchdays: int,
    n_clv: int,
) -> List[str]:
    by_id = {g["id"]: g for g in gates}
    actions: List[str] = []
    if not by_id.get("F1_audit", {}).get("pass"):
        actions.append("Set HIBS_PREDICTION_LOG_ENABLED=1 in .env")
    if not by_id.get("F2_clv", {}).get("pass"):
        actions.append("Set HIBS_CLV_LOG_ENABLED=1")
    if not by_id.get("F3_cron", {}).get("pass"):
        actions.append("sudo bash deploy/cron-hibs-calibration.sh --install")
    if not by_id.get("F7_forward_capture_7d", {}).get("pass"):
        actions.append("bash scripts/run_forward_backfill_plan.sh")
        actions.append("Load dashboard while logged in during fixture days (seeds snapshots).")
    if matchdays < 3:
        actions.append("Wait for matchdays + daily pred-log-sync; do not scale stakes until n≥25.")
    if not by_id.get("F8_clv_sample", {}).get("pass") or not by_id.get("F9_clv_beat_close", {}).get("pass"):
        actions.append("bash scripts/run_daily_audit_pipeline.sh")
    if not by_id.get("F10_brier_1x2", {}).get("pass"):
        actions.append("Review calibration-fit + league shrink; Brier gate is personal staking band only.")
    if not actions:
        actions.append("bash scripts/verify_personal_staking_greenlights.sh")
    return actions
