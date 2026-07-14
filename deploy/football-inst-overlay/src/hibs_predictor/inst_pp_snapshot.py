"""Institutional++ automation snapshot — nine-ten + gates + cron health."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]

_EXPECTED_CRON_MARKERS = (
    "hibs-bet: daily bundle",
    "hibs-bet: seed forward evidence",
    "hibs-bet: hands-off cycle",
    "hibs-bet: institutional++ watchdog",
    "hibs-bet: nine-ten daily",
    "hibs-bet: inst++ weekly",
    "hibs-bet: calibration drift",
    "hibs-racing: sqlite maintenance",
    "hibs-racing",
)


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_www_data_crontab() -> str:
    try:
        proc = subprocess.run(
            ["crontab", "-u", "www-data", "-l"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if proc.returncode == 0:
            return proc.stdout or ""
    except Exception:
        pass
    return ""


def verify_crons_installed() -> dict[str, Any]:
    """Check expected automation markers exist in www-data crontab."""
    text = read_www_data_crontab()
    rows = []
    for marker in _EXPECTED_CRON_MARKERS:
        present = marker in text
        rows.append({"marker": marker, "installed": present})
    installed = sum(1 for r in rows if r["installed"])
    return {
        "ok": installed >= len(_EXPECTED_CRON_MARKERS) - 1,
        "installed": installed,
        "expected": len(_EXPECTED_CRON_MARKERS),
        "markers": rows,
    }


def log_freshness(path: str | Path, *, max_hours: float) -> dict[str, Any]:
    p = Path(path)
    if not p.is_file():
        return {"path": str(p), "ok": False, "message": "missing"}
    age_h = (datetime.now(timezone.utc).timestamp() - p.stat().st_mtime) / 3600.0
    return {
        "path": str(p),
        "ok": age_h <= max_hours,
        "age_hours": round(age_h, 1),
        "max_hours": max_hours,
    }


def automation_health(*, app_root: str | None = None) -> dict[str, Any]:
    root = Path(app_root or os.getenv("DEPLOY_PATH", "/opt/hibs-bet"))
    log_dir = Path(os.getenv("LOG_DIR", "/var/log/hibs-bet"))
    crons = verify_crons_installed()
    checks = {
        "hands_off_cycle": log_freshness(log_dir / "hands-off-cycle.log", max_hours=1.5),
        "institutional_watchdog": log_freshness(log_dir / "institutional-watchdog.log", max_hours=26),
        "daily_audit": log_freshness(log_dir / "daily-audit-am.log", max_hours=30),
        "nine_ten": log_freshness(log_dir / "nine-ten.log", max_hours=26),
        "data_producer_slo": log_freshness(log_dir / "data-producer-slo.json", max_hours=2.0),
    }
    scripts_ok = all(
        (root / rel).is_file()
        for rel in (
            "scripts/hands_off_cycle.sh",
            "scripts/install_hands_off_automation.sh",
            "deploy/cron-hibs-hands-off.sh",
            "deploy/cron-hibs-ops-automation.sh",
        )
    )
    ok = crons["ok"] and scripts_ok and checks["hands_off_cycle"]["ok"]
    return {
        "ok": ok,
        "crons": crons,
        "log_freshness": checks,
        "scripts_ok": scripts_ok,
        "checked_at": _utc_iso(),
    }


def score_nine_ten_vps() -> dict[str, Any]:
    """Full nine-ten on VPS — local production probe + live verify scripts."""
    from hibs_predictor.nine_ten_score import score_all

    return score_all(
        remote_production=None,
        run_remote_verifies=True,
        run_pytest=False,
    )


def build_inst_pp_snapshot(*, include_nine_ten: bool = True) -> dict[str, Any]:
    out: dict[str, Any] = {
        "layer": "institutional_plus_plus",
        "title": "Inst++ automation snapshot",
        "checked_at": _utc_iso(),
        "automation_health": automation_health(),
    }
    try:
        from hibs_predictor.institutional_readiness import readiness_dict

        ir = readiness_dict()
        out["engineering_grade"] = ir.get("engineering_grade")
        out["evidence_grade"] = ir.get("evidence_grade")
        out["buyer_readiness_score"] = ir.get("buyer_readiness_score")
        out["commercial_tier"] = ir.get("commercial_tier")
    except Exception as exc:
        out["readiness_error"] = str(exc)[:120]

    try:
        from hibs_predictor.forward_evidence import forward_evidence_gates

        fwd = forward_evidence_gates()
        out["football"] = {
            "buyer_ready": fwd.get("buyer_ready"),
            "buyer_readiness_score": fwd.get("buyer_readiness_score"),
            "evidence_grade": fwd.get("evidence_grade"),
            "matchdays_7d": fwd.get("matchdays_7d"),
        }
    except Exception as exc:
        out["football"] = {"error": str(exc)[:120]}

    try:
        if os.path.isdir(os.getenv("HIBS_RACING_DEPLOY_PATH", "/opt/hibs-racing")):
            os.environ.setdefault("HIBS_RACING_EVIDENCE_LOCAL", "1")
        from hibs_predictor.racing_evidence import racing_evidence_gates

        rc = racing_evidence_gates()
        out["racing"] = {
            "buyer_ready": rc.get("buyer_ready"),
            "buyer_readiness_score": rc.get("buyer_readiness_score"),
            "evidence_grade": rc.get("evidence_grade"),
        }
    except Exception as exc:
        out["racing"] = {"error": str(exc)[:120]}

    try:
        from hibs_predictor.data_producer_slo import build_data_producer_snapshot

        out["data_producer"] = build_data_producer_snapshot()
    except Exception as exc:
        out["data_producer"] = {"ok": False, "error": str(exc)[:120]}

    if include_nine_ten:
        try:
            nt = score_nine_ten_vps()
            out["nine_ten"] = {
                "average": nt.get("average"),
                "pillars_at_9": nt.get("pillars_at_9"),
                "pillars_total": nt.get("pillars_total"),
                "institutional_ready": nt.get("institutional_ready"),
                "pillars": [
                    {
                        "id": p.get("id"),
                        "score": p.get("score"),
                        "at_target": p.get("at_target"),
                        "gaps": (p.get("gaps") or [])[:3],
                    }
                    for p in (nt.get("pillars") or [])
                ],
            }
        except Exception as exc:
            out["nine_ten"] = {"error": str(exc)[:120]}

    eng = out.get("engineering_grade")
    ev = out.get("evidence_grade")
    nt_avg = (out.get("nine_ten") or {}).get("average")
    auto_ok = (out.get("automation_health") or {}).get("ok")
    if eng in ("A", "B+") and auto_ok:
        inst_tier = "institutional_engineering"
    else:
        inst_tier = "engineering_gaps"
    if out.get("football", {}).get("buyer_ready") and (nt_avg or 0) >= 8.5:
        inst_tier = "institutional_ready"
    out["inst_pp_tier"] = inst_tier
    return out


def maybe_weekly_data_room_export() -> dict[str, Any]:
    """Export B2B data room at most once per week when football buyer_ready."""
    from hibs_predictor.hands_off_guard import rate_limit_ok, record_action

    if not rate_limit_ok("data_room_export", min_hours=168):
        return {"skipped": True, "reason": "rate_limit"}
    try:
        from hibs_predictor.forward_evidence import forward_evidence_gates

        if not forward_evidence_gates().get("buyer_ready"):
            return {"skipped": True, "reason": "football_not_buyer_ready"}
    except Exception as exc:
        return {"skipped": True, "reason": str(exc)[:80]}

    script = _REPO / "scripts" / "export_b2b_data_room.sh"
    if not script.is_file():
        return {"skipped": True, "reason": "missing_export_script"}
    proc = subprocess.run(
        ["bash", str(script)],
        cwd=str(_REPO),
        capture_output=True,
        text=True,
        timeout=600,
    )
    record_action("data_room_export")
    return {
        "exported": proc.returncode == 0,
        "exit_code": proc.returncode,
        "tail": (proc.stdout or proc.stderr or "")[-400:],
    }


def write_status_json(path: str | Path, snapshot: dict[str, Any] | None = None) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    data = snapshot or build_inst_pp_snapshot()
    p.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    return p


def read_cached_inst_pp(*, max_age_hours: float = 2.0) -> dict[str, Any] | None:
    """Read lightweight Inst++ snapshot from disk (written by hands-off cycle)."""
    log_dir = Path(os.getenv("LOG_DIR", "/var/log/hibs-bet"))
    path = log_dir / "inst-pp-status.json"
    if not path.is_file():
        return None
    age_h = (datetime.now(timezone.utc).timestamp() - path.stat().st_mtime) / 3600.0
    if age_h > max_age_hours:
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        data["cache_age_hours"] = round(age_h, 2)
        return data
    except Exception:
        return None


def inst_pp_for_health() -> dict[str, Any]:
    """Fast Inst++ block for /api/health — cached snapshot or live automation_health only."""
    cached = read_cached_inst_pp()
    if cached:
        return {
            "source": "cache",
            "inst_pp_tier": cached.get("inst_pp_tier"),
            "engineering_grade": cached.get("engineering_grade"),
            "evidence_grade": cached.get("evidence_grade"),
            "automation_health": cached.get("automation_health"),
            "football": cached.get("football"),
            "cache_age_hours": cached.get("cache_age_hours"),
            "checked_at": cached.get("checked_at"),
        }
    try:
        health = automation_health()
        return {
            "source": "live",
            "automation_health": health,
            "checked_at": health.get("checked_at"),
        }
    except Exception as exc:
        return {"source": "error", "error": str(exc)[:120]}


if __name__ == "__main__":
    out = build_inst_pp_snapshot()
    if len(sys.argv) > 1 and sys.argv[1] == "--write":
        target = sys.argv[2] if len(sys.argv) > 2 else "/var/log/hibs-bet/inst-pp-status.json"
        write_status_json(target, out)
    print(json.dumps(out, indent=2, default=str))
