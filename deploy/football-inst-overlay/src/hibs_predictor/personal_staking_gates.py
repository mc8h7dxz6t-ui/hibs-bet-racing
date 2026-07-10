"""Personal staking green lights — when YOU may scale stakes (not buyer/sales language).

Industry benchmark references (facts, not claims we meet them):
- Football 1X2 Brier: ~0.20–0.22 random; sharp models often 0.18–0.21 on elite leagues.
- CLV beat-close: descriptive edge signal; ≥50% on n≥25 is a minimum sample gate, not proof.
- Racing place Brier: R8 ≤0.25 on n≥20 settled paper rows.
- ROI: forward_offered plane only for live staking decisions — SP holdout is calibration only.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

FOOTBALL_BRIER_PASS_MAX = 0.22
FOOTBALL_BRIER_MIN_N = 30
RACING_PLACE_BRIER_PASS_MAX = 0.25
RACING_PLACE_BRIER_MIN_N = 20
CLV_MIN_N = 25
CLV_BEAT_CLOSE_PCT = 50.0
MATCHDAYS_MIN = 3
CAPTURE_7D_PCT = 50.0


def _lane_status(*, ready: bool, blockers: List[str], notes: List[str]) -> Dict[str, Any]:
    return {
        "staking_allowed": ready,
        "personal_green_light": ready,
        "blockers": blockers,
        "notes": notes,
    }


def football_staking_greenlight() -> Dict[str, Any]:
    """Personal go/no-go for football 1X2 stakes."""
    blockers: List[str] = []
    notes: List[str] = []
    metrics: Dict[str, Any] = {}

    try:
        from hibs_predictor.forward_evidence import forward_evidence_gates

        fwd = forward_evidence_gates()
        metrics["evidence_grade"] = fwd.get("evidence_grade")
        metrics["matchdays_7d"] = fwd.get("matchdays_7d")
        by_id = {g["id"]: g for g in fwd.get("gates") or []}

        if not fwd.get("critical_pass"):
            blockers.append("football_critical_gates_red")
        for gid in ("F7_forward_capture_7d", "F8_clv_sample", "F9_clv_beat_close"):
            g = by_id.get(gid) or {}
            if not g.get("pass"):
                blockers.append(gid)

        mon: Dict[str, Any] = {}
        try:
            from hibs_predictor.prediction_log import monitor_summary_dict

            mon = monitor_summary_dict()
            metrics["brier_1x2"] = mon.get("brier_score_1x2")
            metrics["n_scored"] = mon.get("n_scored")
            n_scored = int(mon.get("n_scored") or 0)
            brier = mon.get("brier_score_1x2")
            if n_scored < FOOTBALL_BRIER_MIN_N:
                blockers.append(f"football_brier_n<{FOOTBALL_BRIER_MIN_N}")
            elif brier is not None and float(brier) > FOOTBALL_BRIER_PASS_MAX:
                blockers.append(f"football_brier>{FOOTBALL_BRIER_PASS_MAX}")
        except Exception as exc:
            blockers.append(f"football_monitor_unavailable:{str(exc)[:60]}")

        if int(fwd.get("matchdays_7d") or 0) < MATCHDAYS_MIN:
            notes.append("summer/off-season: matchday gates expected red until fixtures return")

        ready = not blockers
        if ready:
            notes.append(
                "Personal green light: critical + F7–F9 + Brier cohort pass. "
                "Start micro-stakes only; scale on continued CLV + Brier, not one week."
            )
        else:
            notes.append("Paper / dashboard only until blockers clear.")

        return {
            **_lane_status(ready=ready, blockers=blockers, notes=notes),
            "lane": "football",
            "metrics": metrics,
            "evidence_gates_complete": bool(fwd.get("evidence_gates_complete", fwd.get("buyer_ready"))),
        }
    except Exception as exc:
        return {
            **_lane_status(ready=False, blockers=[f"football_error:{str(exc)[:80]}"], notes=[]),
            "lane": "football",
            "metrics": metrics,
        }


def racing_staking_greenlight() -> Dict[str, Any]:
    """Personal go/no-go for racing paper → funded transition."""
    blockers: List[str] = []
    notes: List[str] = []
    metrics: Dict[str, Any] = {}

    try:
        import importlib

        mod = importlib.import_module("hibs_racing.evidence_gates")
        rep = mod.racing_evidence_gates()
        metrics["evidence_grade"] = rep.get("evidence_grade")
        by_id = {g["id"]: g for g in rep.get("gates") or []}

        if not rep.get("critical_pass"):
            blockers.append("racing_critical_gates_red")
        for gid in ("R5_coverage", "R6_recon_clean", "R7_paper_sample", "R8_place_brier"):
            g = by_id.get(gid) or {}
            if g and not g.get("pass"):
                blockers.append(gid)

        try:
            from hibs_racing.live.execution_config import EXECUTION_DISABLED

            if EXECUTION_DISABLED:
                notes.append("Live exchange routing disabled (analytics mode) — funded API ≠ auto-stake")
        except ImportError:
            pass

        ready = not blockers
        if ready:
            notes.append("Personal green light: R1–R8 pass. Matchbook funded preflight still required.")
        else:
            notes.append("Observation lane / paper only until R5–R8 pass on live card days.")

        return {
            **_lane_status(ready=ready, blockers=blockers, notes=notes),
            "lane": "racing",
            "metrics": metrics,
            "evidence_gates_complete": bool(rep.get("evidence_gates_complete", rep.get("buyer_ready"))),
        }
    except Exception as exc:
        return {
            **_lane_status(ready=False, blockers=[f"racing_unavailable:{str(exc)[:80]}"], notes=[]),
            "lane": "racing",
            "metrics": metrics,
        }


def trading_staking_greenlight() -> Dict[str, Any]:
    """Shadow trading lane — fund only after forward economic gate (if trading-core present)."""
    blockers: List[str] = ["trading_core_not_verified"]
    notes: List[str] = [
        "trading_core/ is partial in repo — Day-15 gate script may be missing modules.",
        "Default: shadow soak only; no live equity until promotion_scorecard passes on VPS.",
    ]
    trading_root = os.getenv("TRADING_INSTALL_ROOT", "/opt/trading-core")
    if os.path.isdir(trading_root):
        blockers = ["trading_day15_gate_not_run"]
        notes.append(f"Run evaluate_trading_day15_gate.py on {trading_root} after shadow window.")
    return {
        **_lane_status(ready=False, blockers=blockers, notes=notes),
        "lane": "trading",
        "metrics": {"trading_root": trading_root, "exists": os.path.isdir(trading_root)},
    }


def fve_operational_status() -> Dict[str, Any]:
    """FVE is read-only lines — operational, not a staking lane."""
    try:
        from hibs_predictor.data_producer_slo import fve_lines_export_status, fve_remote_status

        export = fve_lines_export_status()
        remote = fve_remote_status()
        ok = bool(export.get("ok")) and bool(remote.get("ok") or remote.get("reachable"))
        return {
            "lane": "fve",
            "operational": ok,
            "fixture_count": export.get("fixture_count"),
            "remote_ok": remote.get("ok"),
            "notes": ["FVE feeds line-trader UI — staking decisions use football CLV gates, not FVE alone."],
        }
    except Exception as exc:
        return {"lane": "fve", "operational": False, "error": str(exc)[:120]}


def personal_staking_report() -> Dict[str, Any]:
    """Unified personal green-light report for verify scripts and /api/health."""
    football = football_staking_greenlight()
    racing = racing_staking_greenlight()
    trading = trading_staking_greenlight()
    fve = fve_operational_status()

    lanes = [football, racing, trading]
    any_ready = any(l.get("personal_green_light") for l in lanes)
    all_data_ok = bool(fve.get("operational"))

    from hibs_predictor.honesty_plane import attach_honesty

    return attach_honesty(
        {
            "personal_project": True,
            "any_lane_staking_green_light": any_ready,
            "fve_operational": all_data_ok,
            "lanes": {
                "football": football,
                "racing": racing,
                "trading": trading,
                "fve": fve,
            },
            "disclaimer": (
                "Personal research infrastructure. Green lights are internal checklists only — "
                "not financial advice, not proof of edge, not regulatory approval to accept stakes."
            ),
        }
    )
