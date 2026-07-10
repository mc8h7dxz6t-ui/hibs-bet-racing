"""Racing institutional evidence gates (R1–R8) — local health, no football overlay."""

from __future__ import annotations

import os
from typing import Any

COVERAGE_PASS_OBS_PCT = 35.0
COVERAGE_PASS_PROD_PCT = 50.0
MIN_PAPER_ROWS = 25
PLACE_BRIER_PASS_MAX = 0.25
MIN_PLACE_CALIBRATION_N = 20


def _gate(
    gate_id: str,
    *,
    label: str,
    passed: bool,
    actual: Any,
    threshold: str,
    message: str = "",
    critical: bool = False,
    **extra: Any,
) -> dict[str, Any]:
    row = {
        "id": gate_id,
        "label": label,
        "pass": passed,
        "actual": actual,
        "threshold": threshold,
        "message": message,
        "critical": critical,
    }
    row.update(extra)
    return row


def _coverage_pct(health: dict[str, Any]) -> float | None:
    tel = health.get("telemetry_balance") or health.get("telemetry") or {}
    if tel.get("coverage_pct") is not None:
        return float(tel["coverage_pct"])
    if health.get("snapshot_coverage_pct") is not None:
        return float(health["snapshot_coverage_pct"])
    return None


def _paper_n(health: dict[str, Any]) -> int | None:
    paper = health.get("paper") or {}
    for key in ("n_rows", "settled", "settled_n"):
        if paper.get(key) is not None:
            return int(paper[key])
    if health.get("paper_rows") is not None:
        return int(health["paper_rows"])
    return None


def racing_evidence_gates_from_health(health: dict[str, Any]) -> dict[str, Any]:
    """Build R1–R8 gates from health_status().to_dict() output."""
    is_prod = os.environ.get("HIBS_PRODUCTION", "").strip().lower() in ("1", "true", "yes", "on")
    cov_threshold = COVERAGE_PASS_PROD_PCT if is_prod else COVERAGE_PASS_OBS_PCT

    db_ok = bool(health.get("db_ok"))
    card_fresh = health.get("card_fresh")
    nan_ok = health.get("nan_integrity_passed")

    coverage = _coverage_pct(health)
    coverage_pass = coverage is not None and float(coverage) >= cov_threshold

    recon = health.get("paper_recon_clean")
    if recon is None:
        recon = health.get("recon_clean")
    recon_pass = recon is True

    paper_n = _paper_n(health)
    paper_pass = paper_n is not None and paper_n >= MIN_PAPER_ROWS

    place_rel = health.get("place_reliability") or {}
    place_brier = place_rel.get("brier")
    place_n = int(place_rel.get("n") or 0)
    brier_pass = (
        place_n >= MIN_PLACE_CALIBRATION_N
        and place_brier is not None
        and float(place_brier) <= PLACE_BRIER_PASS_MAX
    )
    brier_insufficient = place_n < MIN_PLACE_CALIBRATION_N

    dp = health.get("data_producer") or {}
    dp_ok = dp.get("ok") is not False

    gates = [
        _gate(
            "R1_ping",
            label="Process health (db + data producer)",
            passed=db_ok and dp_ok,
            actual={"db_ok": db_ok, "data_producer_ok": dp_ok},
            threshold="db_ok=true, data_producer.ok!=false",
            message="systemctl restart hibs-racing; check data_producer_slo",
            critical=True,
        ),
        _gate(
            "R2_cards",
            label="Card freshness",
            passed=card_fresh is not False,
            actual=card_fresh,
            threshold="card_fresh!=false",
            message="bash scripts/daily_refresh.sh or VPS cron",
            critical=True,
        ),
        _gate(
            "R2b_cards_data",
            label="NaN integrity on card",
            passed=nan_ok is not False,
            actual=nan_ok,
            threshold="nan_integrity_passed!=false",
            message="feature_store refresh — daily_refresh.sh",
            critical=True,
        ),
        _gate(
            "R3_health",
            label="Full health payload",
            passed=bool(health),
            actual=bool(health),
            threshold="health_status dict",
            message="/api/health?full=1",
            critical=True,
        ),
        _gate(
            "R5_coverage",
            label="Telemetry coverage",
            passed=coverage_pass,
            actual=coverage,
            threshold=f">={cov_threshold}%",
            message="telemetry_balance.coverage_pct",
            critical=False,
            window="telemetry",
            coverage_pct=float(coverage) if coverage is not None else None,
        ),
        _gate(
            "R6_recon_clean",
            label="Paper recon clean",
            passed=recon_pass,
            actual=recon,
            threshold="true",
            message="daily_refresh institutional-check --require-recon-clean",
            critical=False,
            window="paper_recon",
        ),
        _gate(
            "R7_paper_sample",
            label="Paper ledger sample",
            passed=paper_pass,
            actual=paper_n,
            threshold=f">={MIN_PAPER_ROWS} rows",
            message="Accumulate --paper picks via daily batch",
            critical=False,
            n=paper_n,
            window="ledger",
        ),
        _gate(
            "R8_place_brier",
            label="Place probability calibration (Brier)",
            passed=brier_pass if not brier_insufficient else False,
            actual=place_brier,
            threshold=f"<={PLACE_BRIER_PASS_MAX} (n>={MIN_PLACE_CALIBRATION_N})",
            message=(
                f"Accumulate {MIN_PLACE_CALIBRATION_N}+ settled place bins — "
                f"current n={place_n}"
                if brier_insufficient
                else "Tighten isotonic calibration or gate selectivity"
            ),
            critical=False,
            n=place_n,
            window="calibration_60d",
            insufficient_sample=brier_insufficient,
        ),
    ]

    critical = [g for g in gates if g.get("critical")]
    evidence = [g for g in gates if not g.get("critical")]
    critical_pass = all(g["pass"] for g in critical)
    evidence_pass = all(g["pass"] for g in evidence)
    passed_n = sum(1 for g in gates if g["pass"])
    ratio = passed_n / max(len(gates), 1)

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

    buyer_ready = critical_pass and evidence_pass
    gate_score = int(round(100.0 * passed_n / max(len(gates), 1)))
    if not critical_pass:
        tier = "pilot_deployable"
    elif evidence_pass and gate_score >= 85:
        tier = "production_license_candidate"
    elif gate_score >= 60:
        tier = "design_partner_evaluation"
    else:
        tier = "pilot_deployable"

    return {
        "gates": gates,
        "critical_pass": critical_pass,
        "evidence_pass": evidence_pass,
        "evidence_grade": grade,
        "buyer_ready": buyer_ready,
        "buyer_readiness_score": gate_score,
        "commercial_tier": tier,
        "next_actions": _next_actions(gates),
    }


def racing_evidence_gates() -> dict[str, Any]:
    from hibs_racing.web_service import health_status

    health = health_status().to_dict()
    out = racing_evidence_gates_from_health(health)
    out["source"] = "local_health"
    return out


def _next_actions(gates: list[dict[str, Any]]) -> list[str]:
    by_id = {g["id"]: g for g in gates}
    actions: list[str] = []
    if not by_id.get("R1_ping", {}).get("pass"):
        actions.append("systemctl restart hibs-racing")
    if not by_id.get("R2_cards", {}).get("pass") or not by_id.get("R2b_cards_data", {}).get("pass"):
        actions.append("bash scripts/daily_refresh.sh")
    if not by_id.get("R5_coverage", {}).get("pass"):
        actions.append("Raise telemetry coverage — daily_refresh + card sync")
    if not by_id.get("R6_recon_clean", {}).get("pass"):
        actions.append("bash scripts/daily_refresh.sh --require-recon-clean")
    if not by_id.get("R7_paper_sample", {}).get("pass"):
        actions.append("Accumulate paper ledger via daily batch picks")
    r8 = by_id.get("R8_place_brier", {})
    if r8 and not r8.get("pass"):
        if r8.get("insufficient_sample"):
            actions.append("Settle more forward paper picks for place Brier gate (R8)")
        else:
            actions.append("Run win-prob-calibration-fit; review place overconfidence")
    if not actions:
        actions.append("bash scripts/export_racing_data_room.sh")
    return actions
