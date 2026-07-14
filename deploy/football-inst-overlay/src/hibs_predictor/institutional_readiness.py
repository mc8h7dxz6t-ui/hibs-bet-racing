"""Engineering + evidence readiness grades for hibs-bet."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Tuple

from dotenv import load_dotenv

_TRIAL_VALUE_LEAGUES_DEFAULT = (
    "EPL,SCOTLAND,UCL,EUROPA_LEAGUE,UECL,LA_LIGA,SERIE_A,BUNDESLIGA,LIGUE_1,EREDIVISIE,PRIMEIRA"
)


def _parse_trial_leagues() -> set[str]:
    load_dotenv()
    raw = (os.getenv("HIBS_VALUE_LEAGUES") or _TRIAL_VALUE_LEAGUES_DEFAULT).strip()
    return {x.strip().upper() for x in raw.split(",") if x.strip()}


_TRIAL_VALUE_LEAGUES: set[str] = _parse_trial_leagues()


def _load_trial_leagues() -> set[str]:
    global _TRIAL_VALUE_LEAGUES
    _TRIAL_VALUE_LEAGUES = _parse_trial_leagues()
    return _TRIAL_VALUE_LEAGUES


def _env_truthy(name: str, default: str = "0") -> bool:
    load_dotenv()
    return (os.getenv(name, default) or "").strip().lower() in ("1", "true", "yes", "on")


def collect_config_issues(*, production: bool = False) -> Tuple[List[str], List[str]]:
    """Return (blocking_issues, warnings) for institutional config."""
    load_dotenv()
    issues: List[str] = []
    warnings: List[str] = []
    prod = production or _env_truthy("HIBS_PRODUCTION")

    if prod and _env_truthy("HIBS_DEV_FULL_DQ"):
        issues.append("HIBS_DEV_FULL_DQ=1 must not be set in production")

    if not _env_truthy("HIBS_PREDICTION_LOG_ENABLED", "1"):
        issues.append("HIBS_PREDICTION_LOG_ENABLED must be 1 for institutional audit")

    if prod:
        from hibs_predictor.prediction_log import _clv_enabled, prediction_log_enabled

        if prediction_log_enabled() and not _clv_enabled():
            warnings.append("HIBS_CLV_LOG_ENABLED=0 — CLV evidence degraded")

        if _env_truthy("HIBS_FETCH_ALL_DOMESTIC"):
            warnings.append("HIBS_FETCH_ALL_DOMESTIC=1 widens fetch — trial VPS should omit")

        if not _env_truthy("HIBS_SHARPEN_GATES"):
            warnings.append("HIBS_SHARPEN_GATES=0 — trial sharpen profile not active")

        trial = _load_trial_leagues()
        expected = {x.strip().upper() for x in _TRIAL_VALUE_LEAGUES_DEFAULT.split(",")}
        if trial != expected and trial != expected | {"WORLD_CUP", "INTL_FRIENDLIES"}:
            missing = sorted(expected - trial)
            if missing:
                warnings.append(f"HIBS_VALUE_LEAGUES missing trial leagues: {', '.join(missing[:4])}")

        from hibs_predictor.historic_calibration import calibration_cache_path

        if not os.path.isfile(calibration_cache_path()):
            warnings.append("calibration_v1.json missing — run calibration-fit after scored rows")

        if _env_truthy("HIBS_AUTH_ENABLED") and not (os.getenv("HIBS_SECRET_KEY") or "").strip():
            issues.append("HIBS_AUTH_ENABLED=1 requires HIBS_SECRET_KEY")

        if _env_truthy("HIBS_AUTH_ENABLED") and not (
            (os.getenv("HIBS_AUTH_PASSWORD") or os.getenv("HIBS_HIBS_PASSWORD") or "").strip()
        ):
            warnings.append("HIBS_AUTH_ENABLED=1 without HIBS_AUTH_PASSWORD")

    return issues, warnings


def _engineering_grade(blocking: List[str], warnings: List[str]) -> str:
    if blocking:
        return "D"
    if not warnings:
        return "A"
    if len(warnings) <= 2:
        return "B+"
    return "B"


def readiness_dict() -> Dict[str, Any]:
    load_dotenv()
    issues, warnings = collect_config_issues(production=_env_truthy("HIBS_PRODUCTION"))
    eng = _engineering_grade(issues, warnings)

    evidence_grade = "C"
    buyer_ready = False
    forward_summary: Dict[str, Any] = {}
    try:
        from hibs_predictor.forward_evidence import forward_evidence_gates

        forward_summary = forward_evidence_gates()
        evidence_grade = forward_summary.get("evidence_grade") or evidence_grade
        buyer_ready = bool(forward_summary.get("buyer_ready"))
    except Exception as exc:
        forward_summary = {"error": str(exc)[:120]}

    nine_ten: Dict[str, Any] = {}
    try:
        from hibs_predictor.nine_ten_score import score_pillars_light

        nine_ten = score_pillars_light(
            engineering_grade=eng,
            evidence_grade=evidence_grade,
            buyer_ready=buyer_ready,
        )
    except Exception as exc:
        nine_ten = {"error": str(exc)[:120], "average": None, "institutional_ready": False}

    return {
        "engineering_grade": eng,
        "evidence_grade": evidence_grade,
        "buyer_ready": buyer_ready,
        "blocking_issues": issues,
        "warnings": warnings,
        "forward_evidence": forward_summary,
        "nine_ten": nine_ten,
        "trial_value_leagues": sorted(_load_trial_leagues()),
    }


def validate_production_config(*, strict: bool = True) -> None:
    issues, _warnings = collect_config_issues(production=True)
    if strict and issues:
        raise RuntimeError("; ".join(issues))


def log_startup_readiness() -> None:
    try:
        rep = readiness_dict()
        print(
            f"[institutional] engineering={rep.get('engineering_grade')} "
            f"evidence={rep.get('evidence_grade')} "
            f"buyer_ready={rep.get('buyer_ready')}"
        )
    except Exception as exc:
        print(f"[institutional] readiness probe skipped: {exc!r}")
