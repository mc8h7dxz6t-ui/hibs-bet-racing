"""Nine-ten institutional pillar scoring (0–10 each)."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

_PILLARS = (
    "football_engineering",
    "football_evidence",
    "football_production",
    "racing_integration",
    "trading_ops",
    "stack_boundaries",
    "b2b_packaging",
    "ops_automation",
)


def _env_truthy(name: str) -> bool:
    return (os.getenv(name) or "").strip().lower() in ("1", "true", "yes", "on")


def _grade_points(grade: str | None) -> float:
    mapping = {"A": 9.5, "B+": 8.5, "B": 7.5, "C+": 6.5, "C": 5.5, "D": 3.0}
    return mapping.get(str(grade or "").upper(), 4.0)


def score_pillars_light(
    *,
    engineering_grade: str | None = None,
    evidence_grade: str | None = None,
    buyer_ready: bool = False,
) -> Dict[str, Any]:
    """Fast pillar estimate without HTTP probes — used by readiness_dict."""
    eng = engineering_grade or "C"
    ev = evidence_grade or "C"
    ev_pts = _grade_points(ev)
    if buyer_ready:
        ev_pts = max(ev_pts, 9.0)
    scores = {
        "football_engineering": _grade_points(eng),
        "football_evidence": ev_pts,
        "football_production": 7.0,
        "racing_integration": 6.0,
        "trading_ops": 6.0,
        "stack_boundaries": 8.0,
        "b2b_packaging": 6.5,
        "ops_automation": 7.0,
    }
    pillar_rows = [{"pillar": p, "score": round(scores[p], 1)} for p in _PILLARS]
    values = [row["score"] for row in pillar_rows]
    average = round(sum(values) / max(len(values), 1), 2)
    return {
        "pillars": pillar_rows,
        "average": average,
        "institutional_ready": average >= 8.5 and ev_pts >= 8.5,
        "mode": "light",
    }


def score_all(
    *,
    remote_production: Optional[str] = None,
    run_remote_verifies: bool = False,
    run_pytest: bool = False,
) -> Dict[str, Any]:
    load_dotenv()
    scores: Dict[str, float] = {}
    notes: Dict[str, str] = {}

    try:
        from hibs_predictor.institutional_readiness import collect_config_issues
        from hibs_predictor.forward_evidence import forward_evidence_gates

        issues, warnings = collect_config_issues(production=_env_truthy("HIBS_PRODUCTION"))
        fwd = forward_evidence_gates()
        eng = "D" if issues else ("A" if not warnings else "B+")
        scores["football_engineering"] = _grade_points(eng)
        scores["football_evidence"] = _grade_points(fwd.get("evidence_grade"))
        if fwd.get("buyer_ready"):
            scores["football_evidence"] = max(scores["football_evidence"], 9.0)
        notes["football_engineering"] = f"grade={eng}"
        notes["football_evidence"] = f"buyer_ready={fwd.get('buyer_ready')}"
    except Exception as exc:
        scores["football_engineering"] = 4.0
        scores["football_evidence"] = 4.0
        notes["football_engineering"] = str(exc)[:80]

    # Production probe — local systemd / ping when not remote
    prod_pts = 7.0
    try:
        import subprocess
        import urllib.request

        url = (remote_production or os.getenv("HIBS_PRODUCTION_URL") or "").strip()
        if url:
            with urllib.request.urlopen(f"{url.rstrip('/')}/api/ping", timeout=8) as resp:
                prod_pts = 9.0 if resp.status == 200 else 6.0
        else:
            proc = subprocess.run(["systemctl", "is-active", "hibs-bet"], capture_output=True, text=True, timeout=5)
            prod_pts = 9.0 if proc.stdout.strip() == "active" else 6.0
    except Exception:
        prod_pts = 5.0
    scores["football_production"] = prod_pts

    try:
        if (os.getenv("HIBS_NINE_TEN_SKIP_RACING_PROBE") or "").strip().lower() in ("1", "true", "yes"):
            raise RuntimeError("racing probe skipped")
        os.environ.setdefault("HIBS_RACING_EVIDENCE_TIMEOUT_PING", "3")
        os.environ.setdefault("HIBS_RACING_EVIDENCE_TIMEOUT_HEALTH", "5")
        os.environ.setdefault("HIBS_RACING_EVIDENCE_TIMEOUT_CARDS", "5")
        from hibs_predictor.racing_evidence import racing_evidence_gates

        rc = racing_evidence_gates()
        scores["racing_integration"] = _grade_points(rc.get("evidence_grade"))
        notes["racing_integration"] = f"buyer_ready={rc.get('buyer_ready')}"
    except Exception as exc:
        scores["racing_integration"] = 5.0
        notes["racing_integration"] = str(exc)[:80]

    scores["trading_ops"] = 6.0
    trading_root = os.getenv("TRADING_INSTALL_ROOT", "/opt/trading-core")
    try:
        import subprocess

        proc = subprocess.run(
            ["systemctl", "is-active", "trading-shadow-soak"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if proc.stdout.strip() == "active":
            scores["trading_ops"] = 8.0
    except Exception:
        pass
    if not os.path.isdir(trading_root):
        scores["trading_ops"] = min(scores["trading_ops"], 5.0)

    scores["stack_boundaries"] = 8.0
    scores["b2b_packaging"] = 6.5

    try:
        from hibs_predictor.inst_pp_snapshot import automation_health

        auto = automation_health()
        scores["ops_automation"] = 9.0 if auto.get("ok") else 7.0
        notes["ops_automation"] = f"scripts_ok={auto.get('scripts_ok')}"
    except Exception as exc:
        scores["ops_automation"] = 6.0
        notes["ops_automation"] = str(exc)[:80]

    if run_pytest:
        try:
            import subprocess

            root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            proc = subprocess.run(
                ["python3", "-m", "pytest", "tests/", "-q", "--tb=no"],
                cwd=root,
                capture_output=True,
                timeout=300,
            )
            if proc.returncode == 0:
                scores["football_engineering"] = max(scores.get("football_engineering", 0), 9.0)
        except Exception:
            pass

    pillar_rows: List[Dict[str, Any]] = [
        {"pillar": p, "score": round(scores.get(p, 5.0), 1), "note": notes.get(p, "")} for p in _PILLARS
    ]
    values = [row["score"] for row in pillar_rows]
    average = round(sum(values) / max(len(values), 1), 2)
    institutional_ready = average >= 8.5 and scores.get("football_evidence", 0) >= 8.5

    return {
        "pillars": pillar_rows,
        "average": average,
        "institutional_ready": institutional_ready,
        "remote_production": remote_production,
        "run_remote_verifies": run_remote_verifies,
    }
