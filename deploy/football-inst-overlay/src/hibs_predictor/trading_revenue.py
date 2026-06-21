"""Harvested Execution revenue surface — PnL, phase caps, promotion tier."""

from __future__ import annotations

import os
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from hibs_predictor.trading_core.evidence_pack import EvidencePaths
from hibs_predictor.trading_core.promotion_scorecard import (
    PromotionScorecard,
    PromotionTransition,
    ScorecardThresholds,
    count_clean_manifest_days,
    evaluate_promotion_scorecard,
    load_daily_manifests,
)

_PHASE_LIMITS: dict[str, dict[str, Any]] = {
    "paper": {
        "label": "Paper",
        "max_order_usd": 1000,
        "max_gross_usd": 10000,
        "broker_submit": True,
    },
    "shadow": {
        "label": "Shadow soak",
        "max_order_usd": 0,
        "max_gross_usd": 0,
        "broker_submit": False,
    },
    "micro": {
        "label": "Micro-capital",
        "max_order_usd": 100,
        "max_gross_usd": 500,
        "broker_submit": True,
    },
    "live": {
        "label": "Live",
        "max_order_usd": 15000,
        "max_gross_usd": 50000,
        "broker_submit": True,
    },
}

_PORT_PHASE = {
    9108: "shadow",
    9109: "paper",
    9110: "micro",
}

_TIER_LABELS = {
    "pilot_deployable": "Pilot R&D",
    "design_partner_evaluation": "Design partner",
    "production_license_candidate": "Revenue-ready",
    "micro_capital_active": "Micro-capital live",
}


def trading_install_root() -> Path:
    return Path(os.getenv("TRADING_INSTALL_ROOT", "/opt/trading-core"))


def infer_phase(*, metrics_url: str, env_phase: str | None = None) -> str:
    phase = (env_phase or os.getenv("TRADING_DEPLOYMENT_PHASE") or "paper").strip().lower()
    try:
        port = urlparse(metrics_url).port
        if port in _PORT_PHASE:
            return _PORT_PHASE[port]
    except Exception:
        pass
    if phase in _PHASE_LIMITS:
        return phase
    return "paper"


def phase_limits(phase: str) -> dict[str, Any]:
    return dict(_PHASE_LIMITS.get(phase, _PHASE_LIMITS["paper"]))


def _dec_sum(values: list[Any]) -> Decimal | None:
    total = Decimal("0")
    seen = False
    for raw in values:
        if raw is None or raw == "":
            continue
        try:
            total += Decimal(str(raw))
            seen = True
        except (InvalidOperation, ValueError):
            continue
    return total if seen else None


def build_revenue_block(
    *,
    portfolio: dict[str, Any],
    phase: str,
) -> dict[str, Any]:
    perf = portfolio.get("performance") or {}
    account = portfolio.get("account") or {}
    equity_pos = portfolio.get("equity_positions") or []
    crypto_pos = portfolio.get("crypto_positions") or []
    all_pos = list(equity_pos) + list(crypto_pos)
    unrealized = _dec_sum([p.get("unrealized_pl") for p in all_pos])
    limits = phase_limits(phase)
    base_url = (os.getenv("ALPACA_BASE_URL") or "").lower()
    if "paper-api" in base_url:
        broker_lane = "alpaca_paper"
    elif "api.alpaca" in base_url:
        broker_lane = "alpaca_live"
    else:
        broker_lane = "alpaca_paper" if account.get("paper") else "unknown"

    return {
        "phase": phase,
        "phase_label": limits.get("label"),
        "limits": {
            "max_order_usd": limits.get("max_order_usd"),
            "max_gross_usd": limits.get("max_gross_usd"),
            "broker_submit": limits.get("broker_submit"),
        },
        "equity": perf.get("equity") or account.get("equity"),
        "cash": account.get("cash"),
        "day_pnl": perf.get("day_pnl") or account.get("day_pnl"),
        "day_pnl_pct": perf.get("day_pnl_pct") or account.get("day_pnl_pct"),
        "buying_power": perf.get("buying_power") or account.get("buying_power"),
        "unrealized_pl_total": str(unrealized) if unrealized is not None else None,
        "position_count": len(all_pos),
        "broker_lane": broker_lane,
        "portfolio_available": bool(portfolio.get("available")),
    }


def _scorecard_summary(card: PromotionScorecard) -> dict[str, Any]:
    critical = [c for c in card.checks if c.severity == "critical"]
    warnings = [c for c in card.checks if c.severity == "warning"]
    return {
        "transition": card.transition.value,
        "passed": card.passed,
        "evaluated_at": card.evaluated_at,
        "summary": card.summary,
        "critical_pass": all(c.passed for c in critical),
        "critical_failed": sum(1 for c in critical if not c.passed),
        "warning_failed": sum(1 for c in warnings if not c.passed),
        "checks": [
            {
                "id": c.id,
                "requirement": c.requirement,
                "actual": c.actual,
                "passed": c.passed,
                "severity": c.severity,
            }
            for c in card.checks
        ],
    }


def evaluate_promotion_surface(
    *,
    install_root: Path | None = None,
    shadow_metrics_url: str | None = None,
    active_metrics_url: str | None = None,
    micro_pnl_pct: float | None = None,
) -> dict[str, Any]:
    """Non-fatal promotion evaluation for dashboard (missing artifacts → partial)."""
    root = install_root or trading_install_root()
    data = root / "data"
    daily_dir = data / "evidence" / "daily"
    shadow_url = (shadow_metrics_url or os.getenv("TRADING_SHADOW_METRICS_URL") or "http://127.0.0.1:9108").rstrip(
        "/"
    )
    active_url = (active_metrics_url or os.getenv("TRADING_METRICS_URL") or "http://127.0.0.1:9109").rstrip("/")

    paths = EvidencePaths(
        db_path=Path(os.getenv("TRADING_SHADOW_SOAK_DB", str(data / "trading_shadow_soak.db"))),
        shadow_soak_audit=Path(os.getenv("TRADING_SHADOW_SOAK_AUDIT", str(data / "shadow_soak_audit.log"))),
        strategy_audit=Path(os.getenv("TRADING_STRATEGY_AUDIT", str(data / "strategy_scan_audit.jsonl"))),
        spread_audit=Path(os.getenv("TRADING_SPREAD_AUDIT", str(data / "spread_slippage_audit.jsonl"))),
    )
    micro_paths = EvidencePaths(
        db_path=Path(os.getenv("TRADING_MICRO_DB", str(data / "trading_micro.db"))),
        shadow_soak_audit=paths.shadow_soak_audit,
        strategy_audit=Path(os.getenv("TRADING_MICRO_STRATEGY_AUDIT", str(data / "strategy_scan_micro.jsonl"))),
        spread_audit=Path(os.getenv("TRADING_MICRO_SPREAD_AUDIT", str(data / "spread_slippage_micro.jsonl"))),
    )
    thresholds = ScorecardThresholds()

    manifests = load_daily_manifests(daily_dir)
    clean_days = count_clean_manifest_days(manifests)

    out: dict[str, Any] = {
        "install_root": str(root),
        "evidence_daily_dir": str(daily_dir),
        "clean_shadow_days": clean_days,
        "clean_shadow_days_required": thresholds.min_shadow_clean_days,
        "manifest_days_total": len(manifests),
        "shadow_to_micro": None,
        "micro_to_live": None,
        "error": None,
    }

    try:
        shadow_card = evaluate_promotion_scorecard(
            transition=PromotionTransition.SHADOW_TO_MICRO,
            paths=paths,
            evidence_daily_dir=daily_dir,
            metrics_url=shadow_url,
            thresholds=thresholds,
            phase3_gate_passed=True,
        )
        out["shadow_to_micro"] = _scorecard_summary(shadow_card)
    except Exception as exc:
        out["error"] = str(exc)[:200]

    try:
        micro_card = evaluate_promotion_scorecard(
            transition=PromotionTransition.MICRO_TO_LIVE,
            paths=micro_paths,
            evidence_daily_dir=daily_dir,
            metrics_url=active_url if "9110" in active_url else None,
            thresholds=thresholds,
            micro_pnl_pct=micro_pnl_pct,
        )
        out["micro_to_live"] = _scorecard_summary(micro_card)
    except Exception as exc:
        if not out.get("error"):
            out["error"] = str(exc)[:200]

    return out


def trading_commercial_tier(
    *,
    phase: str,
    online: bool,
    promotion: dict[str, Any],
    revenue: dict[str, Any],
) -> dict[str, Any]:
    """Map promotion progress to a commercial-style tier chip for the dashboard."""
    clean = int(promotion.get("clean_shadow_days") or 0)
    required = int(promotion.get("clean_shadow_days_required") or 30)
    shadow_card = promotion.get("shadow_to_micro") or {}
    micro_card = promotion.get("micro_to_live") or {}

    score = 35
    if online:
        score += 15
    score += min(25, int(clean / max(required, 1) * 25))
    if shadow_card.get("critical_pass"):
        score = max(score, 75)
    if shadow_card.get("passed"):
        score = max(score, 85)

    tier = "pilot_deployable"
    if phase == "micro" and online:
        tier = "micro_capital_active"
        score = max(score, 70)
    elif shadow_card.get("passed"):
        tier = "production_license_candidate"
    elif clean >= 7 or score >= 55:
        tier = "design_partner_evaluation"

    day_pct = revenue.get("day_pnl_pct")
    try:
        if day_pct is not None and float(day_pct) > 0 and phase in ("micro", "live"):
            score = min(100, score + 5)
    except (TypeError, ValueError):
        pass

    next_action = "Run shadow soak + daily evidence collection."
    if clean < required:
        next_action = f"Accumulate clean shadow days ({clean}/{required}) — calendar-bound."
    elif not shadow_card.get("passed"):
        next_action = "Fix failing shadow→micro scorecard checks before micro install."
    elif phase != "micro":
        next_action = "Install micro phase: sudo bash deploy/install-harvested-execution-micro.sh"
    elif not micro_card.get("passed"):
        next_action = "Run micro-capital for 30 days with positive PnL before live promotion."
    else:
        next_action = "Micro→live scorecard green — operator sign-off for live capital."

    return {
        "tier": tier,
        "tier_label": _TIER_LABELS.get(tier, tier.replace("_", " ")),
        "score": min(100, score),
        "next_action": next_action,
        "active_transition": (
            "micro_to_live"
            if phase == "micro"
            else "shadow_to_micro"
        ),
    }


def build_promotion_bundle(
    *,
    metrics_url: str,
    env_phase: str | None,
    portfolio: dict[str, Any],
    online: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    phase = infer_phase(metrics_url=metrics_url, env_phase=env_phase)
    revenue = build_revenue_block(portfolio=portfolio, phase=phase)
    micro_pnl = None
    try:
        if revenue.get("day_pnl_pct") is not None:
            micro_pnl = float(revenue["day_pnl_pct"])
    except (TypeError, ValueError):
        micro_pnl = None

    promotion = evaluate_promotion_surface(
        active_metrics_url=metrics_url,
        micro_pnl_pct=micro_pnl if phase == "micro" else None,
    )
    tier = trading_commercial_tier(
        phase=phase,
        online=online,
        promotion=promotion,
        revenue=revenue,
    )
    promotion.update(tier)
    return revenue, promotion
