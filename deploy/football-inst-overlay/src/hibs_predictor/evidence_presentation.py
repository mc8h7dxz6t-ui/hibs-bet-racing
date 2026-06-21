"""Three-layer evidence presentation: system / statistical / commercial truth."""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Any

STACK_MATURITY: dict[str, dict[str, str]] = {
    "football": {
        "role": "primary_evidence_system",
        "label": "Primary evidence system",
        "note": "Most mature forward audit + CLV pipeline.",
    },
    "racing": {
        "role": "secondary_evidence_system",
        "label": "Secondary evidence system",
        "note": "Operational value lane; lighter institutional evidence than football.",
    },
    "trading": {
        "role": "experimental_rd",
        "label": "Experimental R&D system",
        "note": "Shadow soak + paper — not production capital validation.",
    },
}

COMMERCIAL_TIERS = (
    "pilot_deployable",
    "design_partner_evaluation",
    "production_license_candidate",
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def gate_row(
    gate_id: str,
    *,
    label: str,
    passed: bool,
    actual: Any,
    threshold: str,
    message: str = "",
    critical: bool = False,
    n: int | None = None,
    window: str | None = None,
    coverage_pct: float | None = None,
    last_updated_iso: str | None = None,
) -> dict[str, Any]:
    """Standard gate with statistical honesty fields."""
    checked = last_updated_iso or _utc_now_iso()
    freshness_hours: float | None = None
    try:
        updated = datetime.fromisoformat(checked.replace("Z", "+00:00"))
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
        freshness_hours = round(
            (datetime.now(timezone.utc) - updated.astimezone(timezone.utc)).total_seconds() / 3600.0,
            1,
        )
    except ValueError:
        pass

    display_threshold = threshold
    if n is not None or window or coverage_pct is not None:
        parts = [threshold]
        if n is not None:
            parts.append(f"n={n}")
        if window:
            parts.append(f"window={window}")
        if coverage_pct is not None:
            parts.append(f"coverage={coverage_pct}%")
        display_threshold = " · ".join(parts)

    return {
        "id": gate_id,
        "label": label,
        "pass": bool(passed),
        "actual": actual,
        "threshold": threshold,
        "threshold_display": display_threshold,
        "message": message,
        "critical": critical,
        "n": n,
        "window": window,
        "coverage_pct": coverage_pct,
        "last_updated_iso": checked,
        "freshness_hours": freshness_hours,
        "staleness": _freshness_label(freshness_hours),
    }


def _freshness_label(freshness_hours: float | None) -> str:
    if freshness_hours is None:
        return "unknown"
    if freshness_hours <= 24:
        return "fresh"
    if freshness_hours <= 72:
        return "aging"
    return "stale"


def score_gates(gates: list[dict[str, Any]]) -> int:
    """0–100 from gate pass ratio (critical gates weighted double)."""
    if not gates:
        return 0
    weight = 0.0
    earned = 0.0
    for g in gates:
        w = 2.0 if g.get("critical") else 1.0
        weight += w
        if g.get("pass"):
            earned += w
    return int(round(100.0 * earned / max(weight, 1.0)))


def buyer_readiness_bundle(
    *,
    gates: list[dict[str, Any]],
    critical_pass: bool,
    evidence_pass: bool,
    vertical: str,
) -> dict[str, Any]:
    """Derived readiness — keeps buyer_ready boolean for compatibility."""
    gate_score = score_gates(gates)
    football_score = gate_score if vertical == "football" else None
    racing_score = gate_score if vertical == "racing" else None
    trading_score = gate_score if vertical == "trading" else None
    buyer_ready = bool(critical_pass and evidence_pass)
    tier = commercial_tier(gate_score, critical_pass=critical_pass, evidence_pass=evidence_pass)
    return {
        "buyer_ready": buyer_ready,
        "buyer_readiness_score": gate_score,
        "football_score": football_score,
        "racing_score": racing_score,
        "trading_score": trading_score,
        "commercial_tier": tier,
        "buyer_ready_derived": buyer_ready,
    }


def commercial_tier(
    score: int,
    *,
    critical_pass: bool,
    evidence_pass: bool,
) -> str:
    if not critical_pass:
        return "pilot_deployable"
    if evidence_pass and score >= 85:
        return "production_license_candidate"
    if score >= 60:
        return "design_partner_evaluation"
    return "pilot_deployable"


def status_tier(
    *,
    online: bool,
    critical_issues: int = 0,
    warnings: int = 0,
    anomalies: int = 0,
) -> str:
    """
    GREEN stable · GREEN+ stable with monitored anomalies · AMBER degraded · RED down.
    """
    if not online or critical_issues > 0:
        return "red"
    if warnings > 2 or anomalies > 0:
        return "amber"
    if warnings > 0:
        return "green_plus"
    return "green"


def build_system_status(
    *,
    apis: list[dict[str, Any]] | None = None,
    scrapers: list[dict[str, Any]] | None = None,
    cron_health: list[dict[str, Any]] | None = None,
    failures: dict[str, Any] | None = None,
    ping_ok: bool = True,
) -> dict[str, Any]:
    """Layer A — engineering truth (ping, uptime, API, cron)."""
    apis = apis or []
    scrapers_list = scrapers or []
    api_ok = all(a.get("ok") for a in apis) if apis else True
    scraper_ok = all(s.get("ok") for s in scrapers_list) if scrapers_list else True
    cron_rows = cron_health or []
    cron_degraded = sum(1 for c in cron_rows if c.get("status") not in ("OK",))
    tier = status_tier(
        online=ping_ok and api_ok,
        warnings=cron_degraded + (0 if scraper_ok else 1),
        anomalies=sum(1 for c in cron_rows if c.get("status") == "LATE"),
    )
    return {
        "layer": "system_status",
        "title": "System status (engineering truth)",
        "status_tier": tier,
        "ping_ok": ping_ok,
        "api_health_ok": api_ok,
        "scraper_health_ok": scraper_ok,
        "cron_health": cron_rows,
        "recent_failures": failures or {},
        "checked_at": _utc_now_iso(),
    }


def build_evidence_status(
    *,
    forward: dict[str, Any] | None = None,
    racing: dict[str, Any] | None = None,
    calibration_drift: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Layer B — statistical truth (gates with n, window, coverage)."""
    forward = forward or {}
    racing = racing or {}
    stacks = {
        "football": {
            **STACK_MATURITY["football"],
            "gates": forward.get("gates") or [],
            "evidence_grade": forward.get("evidence_grade"),
            "buyer_readiness_score": forward.get("buyer_readiness_score"),
            "buyer_ready": forward.get("buyer_ready"),
        },
        "racing": {
            **STACK_MATURITY["racing"],
            "gates": racing.get("gates") or [],
            "evidence_grade": racing.get("evidence_grade"),
            "buyer_readiness_score": racing.get("buyer_readiness_score"),
            "buyer_ready": racing.get("buyer_ready"),
        },
    }
    drift_status = (calibration_drift or {}).get("status", "unknown")
    tier = "green"
    if drift_status == "amber":
        tier = "green_plus"
    elif drift_status == "red":
        tier = "amber"
    return {
        "layer": "evidence_status",
        "title": "Evidence status (statistical truth)",
        "status_tier": tier,
        "stacks": stacks,
        "calibration_drift": calibration_drift,
        "checked_at": _utc_now_iso(),
    }


def build_commercial_readiness(
    *,
    forward: dict[str, Any] | None = None,
    racing: dict[str, Any] | None = None,
    trading_maturity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Layer C — market truth (pilot / design partner / license candidate)."""
    forward = forward or {}
    racing = racing or {}
    fb_tier = forward.get("commercial_tier", "pilot_deployable")
    rc_tier = racing.get("commercial_tier", "pilot_deployable")
    scores = {
        "football": forward.get("buyer_readiness_score"),
        "racing": racing.get("buyer_readiness_score"),
        "trading": (trading_maturity or {}).get("buyer_readiness_score"),
    }
    overall = int(
        round(
            sum(s for s in scores.values() if s is not None) / max(len([s for s in scores.values() if s is not None]), 1)
        )
    )
    return {
        "layer": "commercial_readiness",
        "title": "Commercial readiness (market truth)",
        "disclaimer": (
            "Deployable in pilot context ≠ proven edge or production ROI. "
            "License-ready applies only in controlled evaluation with green evidence gates."
        ),
        "football_tier": fb_tier,
        "racing_tier": rc_tier,
        "trading_tier": "pilot_deployable",
        "overall_readiness_score": overall,
        "buyer_ready_football": bool(forward.get("buyer_ready")),
        "buyer_ready_racing": bool(racing.get("buyer_ready")),
        "pilot_deployable_today": bool(forward.get("critical_pass") or racing.get("critical_pass")),
        "checked_at": _utc_now_iso(),
    }


def trading_safety_layers(
    *,
    metrics: dict[str, Any],
    phase: str = "shadow",
    clean_shadow_days: int | None = None,
    clean_shadow_required: int | None = None,
    shadow_to_micro_passed: bool | None = None,
) -> dict[str, Any]:
    """Group trading signals: invariants (hard) vs observability (soft) vs promotion."""
    shadow_would = metrics.get("trading_strategy_shadow_would_route_total") or 0
    routed = metrics.get("trading_strategy_routed_total") or 0
    drifts = metrics.get("trading_reconciliation_drifts_total") or 0
    stale = metrics.get("trading_stale_feed_ms")
    clean_actual = clean_shadow_days if clean_shadow_days is not None else "—"
    clean_need = clean_shadow_required if clean_shadow_required is not None else 30
    invariants = [
        {
            "id": "INV_NO_ROUTED_SHADOW",
            "label": "No ROUTED orders in shadow",
            "pass": routed == 0 if phase == "shadow" else True,
            "actual": routed,
            "threshold": "0 in shadow",
        },
        {
            "id": "INV_WAL_SHADOW",
            "label": "WAL live rows = 0 in shadow",
            "pass": True,
            "actual": "see evidence_pack",
            "threshold": "0 live WAL rows",
            "message": "Verified daily via collect_trading_evidence --fail-on-invariant",
        },
    ]
    observability = [
        {
            "id": "OBS_RECON_DRIFT",
            "label": "Reconciliation drift",
            "value": drifts,
            "ok": drifts == 0,
        },
        {
            "id": "OBS_FEED_STALE",
            "label": "Feed stale (ms)",
            "value": stale,
            "ok": stale is None or float(stale) < 5000,
        },
        {
            "id": "OBS_SHADOW_WOULD_ROUTE",
            "label": "Shadow would-route counter",
            "value": shadow_would,
            "ok": True,
        },
    ]
    promotion = [
        {
            "id": "PROMO_CLEAN_DAYS",
            "label": "Clean shadow days",
            "threshold": str(clean_need),
            "actual": str(clean_actual),
            "passed": isinstance(clean_shadow_days, int) and clean_shadow_days >= int(clean_need),
        },
        {
            "id": "PROMO_SHADOW_TO_MICRO",
            "label": "Shadow→micro scorecard",
            "threshold": "GO",
            "actual": "GO" if shadow_to_micro_passed else "NO-GO",
            "passed": bool(shadow_to_micro_passed),
        },
    ]
    return {
        "phase": phase,
        "maturity": STACK_MATURITY["trading"],
        "invariants": invariants,
        "observability": observability,
        "promotion_conditions": promotion,
    }


_CRON_MANIFEST: list[dict[str, Any]] = [
    {
        "id": "daily_audit_am",
        "log": "/var/log/hibs-bet/daily-audit-am.log",
        "interval_hours": 24,
    },
    {
        "id": "daily_audit_pm",
        "log": "/var/log/hibs-bet/daily-audit-pm.log",
        "interval_hours": 24,
    },
    {
        "id": "calibration_fit",
        "log": "/var/log/hibs-bet/calibration-fit.log",
        "interval_hours": 168,
    },
    {
        "id": "institutional_watchdog",
        "log": "/var/log/hibs-bet/institutional-watchdog.log",
        "interval_hours": 24,
    },
    {
        "id": "racing_daily_refresh",
        "log": "/var/log/hibs-racing/daily-refresh.log",
        "interval_hours": 8,
    },
    {
        "id": "racing_watchdog",
        "log": "/var/log/hibs-racing/watchdog.log",
        "interval_hours": 0.25,
    },
    {
        "id": "value_lane_slo",
        "log": "/var/log/hibs-racing/value-lane-slo.log",
        "interval_hours": 1,
    },
    {
        "id": "hands_off_cycle",
        "log": "/var/log/hibs-bet/hands-off-cycle.log",
        "interval_hours": 0.5,
    },
    {
        "id": "seed_forward_evidence",
        "log": "/var/log/hibs-bet/seed-forward.log",
        "interval_hours": 12,
    },
    {
        "id": "calibration_drift",
        "log": "/var/log/hibs-bet/calibration-drift.log",
        "interval_hours": 24,
    },
    {
        "id": "shadow_paper_recon",
        "log": "/var/log/trading-core/shadow-paper-recon.log",
        "interval_hours": 24,
    },
]


def cron_job_status(log_path: str, *, interval_hours: float) -> dict[str, Any]:
    if not os.path.isfile(log_path):
        return {
            "log": log_path,
            "status": "SKIPPED",
            "message": "log missing",
            "last_run_iso": None,
            "age_hours": None,
        }
    mtime = os.path.getmtime(log_path)
    age_h = (datetime.now(timezone.utc).timestamp() - mtime) / 3600.0
    last_iso = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
    grace = max(interval_hours * 2.5, 1.0)
    if age_h <= interval_hours * 1.5:
        status = "OK"
    elif age_h <= grace:
        status = "LATE"
    else:
        status = "DEGRADED"
    return {
        "log": log_path,
        "status": status,
        "last_run_iso": last_iso,
        "age_hours": round(age_h, 1),
        "expected_interval_hours": interval_hours,
    }


def cron_health_summary() -> list[dict[str, Any]]:
    rows = []
    for job in _CRON_MANIFEST:
        row = cron_job_status(job["log"], interval_hours=float(job["interval_hours"]))
        row["id"] = job["id"]
        rows.append(row)
    return rows


_FAIL_PATTERNS = (
    re.compile(r"(?i)\b(error|fail|fatal|drift_alert|DRIFT_ALERT)\b"),
    re.compile(r"(?i)\bWARN:.*(RED|failed|denied)\b"),
)


def _tail_failures(log_path: str, *, limit: int = 3) -> list[str]:
    if not os.path.isfile(log_path):
        return []
    try:
        with open(log_path, encoding="utf-8", errors="replace") as handle:
            lines = handle.readlines()[-400:]
    except OSError:
        return []
    hits: list[str] = []
    for line in reversed(lines):
        text = line.strip()
        if not text:
            continue
        if any(p.search(text) for p in _FAIL_PATTERNS):
            hits.append(text[:240])
        if len(hits) >= limit:
            break
    return list(reversed(hits))


def failure_visibility_summary() -> dict[str, Any]:
    """Last failures per subsystem — containment visibility, not hiding instability."""
    subs = {
        "football": "/var/log/hibs-bet/daily-audit-am.log",
        "racing": "/var/log/hibs-racing/daily-refresh.log",
        "trading_shadow": "/var/log/trading-core/shadow-paper-recon.log",
        "institutional": "/var/log/hibs-bet/institutional-watchdog.log",
    }
    out: dict[str, Any] = {}
    for name, path in subs.items():
        out[name] = _tail_failures(path, limit=3)
    return {
        "title": "Recent failures (last 3 per subsystem)",
        "subsystems": out,
        "checked_at": _utc_now_iso(),
    }



def build_thirty_day_playbook(
    *,
    forward: dict[str, Any] | None = None,
    racing: dict[str, Any] | None = None,
    trading_day15: dict[str, Any] | None = None,
    system: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Operator priorities for the next 30 days — surfaces gate next_actions."""
    forward = forward or {}
    racing = racing or {}
    priorities: list[dict[str, str]] = []
    actions: list[str] = []

    for src, vertical in ((forward, "football"), (racing, "racing")):
        for act in src.get("next_actions") or []:
            actions.append(f"[{vertical}] {act}")
        score = src.get("buyer_readiness_score")
        if not src.get("buyer_ready"):
            priorities.append(
                {
                    "id": f"{vertical}_evidence",
                    "label": f"{vertical.title()} evidence gates",
                    "tone": "warn",
                    "detail": f"score {score}/100 · tier {src.get('commercial_tier', 'pilot_deployable')}",
                }
            )

    d15 = trading_day15 or {}
    verdict = str(d15.get("verdict") or "")
    if verdict:
        priorities.append(
            {
                "id": "trading_day15",
                "label": "Trading Day-15 gate",
                "tone": "ok" if verdict == "PASS" else ("warn" if verdict == "INCONCLUSIVE" else "bad"),
                "detail": verdict
                + (": " + "; ".join(d15.get("reasons") or []) if d15.get("reasons") else ""),
            }
        )

    cron_bad = [
        c for c in (system or {}).get("cron_health") or [] if c.get("status") not in ("OK",)
    ]
    if cron_bad:
        priorities.append(
            {
                "id": "cron_health",
                "label": "Cron health",
                "tone": "warn",
                "detail": ", ".join(f"{c.get('id')}:{c.get('status')}" for c in cron_bad[:4]),
            }
        )
        actions.append("sudo bash deploy/cron-hibs-ops-automation.sh --install")

    if not actions:
        actions.append("Export data room: bash scripts/export_b2b_data_room.sh")

    return {
        "layer": "thirty_day_playbook",
        "title": "30-day ops playbook",
        "model": "telemetry → evidence → statistical interpretation → commercial tier",
        "priorities": priorities[:6],
        "next_actions": actions[:10],
        "checked_at": _utc_now_iso(),
    }


def attach_three_layers(
    health: dict[str, Any],
    *,
    forward: dict[str, Any] | None = None,
    racing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Merge A/B/C layers onto /api/health payload."""
    apis = health.get("apis") or []
    scrapers = health.get("scrapers") or []
    audit_ops = health.get("audit_ops") or {}
    ping_ok = all(a.get("ok") for a in apis if a.get("id") == "api_football") if apis else True
    if not apis:
        ping_ok = True

    cron_rows = cron_health_summary()
    failures = failure_visibility_summary()
    calibration_drift = audit_ops.get("calibration_drift")

    system = build_system_status(
        apis=apis,
        scrapers=scrapers,
        cron_health=cron_rows,
        failures=failures,
        ping_ok=ping_ok,
    )
    evidence = build_evidence_status(
        forward=forward,
        racing=racing,
        calibration_drift=calibration_drift,
    )
    commercial = build_commercial_readiness(forward=forward, racing=racing)

    trading_day15: dict[str, Any] = {}
    try:
        from dotenv import load_dotenv as _ld

        _ld()
        import os as _os

        if _os.getenv("HIBS_HEALTH_TRADING_DAY15", "").strip().lower() in ("1", "true", "yes", "on"):
            import subprocess
            import sys
            from pathlib import Path

            root = Path(__file__).resolve().parents[2]
            script = root / "scripts" / "evaluate_trading_day15_gate.py"
            if script.is_file():
                proc = subprocess.run(
                    [sys.executable, str(script), "--json"],
                    capture_output=True,
                    text=True,
                    timeout=20,
                    cwd=str(root),
                )
                if proc.stdout.strip():
                    import json as _json

                    trading_day15 = _json.loads(proc.stdout)
    except Exception:
        pass

    playbook = build_thirty_day_playbook(
        forward=forward,
        racing=racing,
        trading_day15=trading_day15,
        system=system,
    )

    health["presentation"] = {
        "model": "telemetry → evidence → statistical interpretation → commercial tier",
        "system_status": system,
        "evidence_status": evidence,
        "commercial_readiness": commercial,
        "thirty_day_playbook": playbook,
        "trading_day15": trading_day15,
        "stack_maturity": STACK_MATURITY,
    }
    try:
        from hibs_predictor.inst_pp_snapshot import inst_pp_for_health

        health["presentation"]["inst_pp"] = inst_pp_for_health()
    except Exception:
        pass
    return health
