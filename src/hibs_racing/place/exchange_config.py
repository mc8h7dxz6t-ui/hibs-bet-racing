"""Exchange place EV + Kelly runtime config (yaml + env overrides)."""

from __future__ import annotations

import os
from typing import Any


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except ValueError:
        return default


def exchange_runtime_config(paper_cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    paper = paper_cfg or {}
    return {
        "exchange_commission": _env_float(
            "HIBS_EXCHANGE_COMMISSION", float(paper.get("exchange_commission", 0.02))
        ),
        "kelly_fraction": _env_float("HIBS_KELLY_FRACTION", float(paper.get("kelly_fraction", 0.25))),
        "max_runner_risk_pct": _env_float(
            "HIBS_MAX_RUNNER_RISK_PCT", float(paper.get("max_runner_risk_pct", 0.02))
        ),
        "exchange_ev_min_coverage_pct": _env_float(
            "HIBS_EXCHANGE_EV_MIN_COVERAGE_PCT",
            float(paper.get("exchange_ev_min_coverage_pct", 50.0)),
        ),
        "exchange_ev_min_settled": int(paper.get("exchange_ev_min_settled", 100)),
        "exchange_ev_shadow": _env_bool("HIBS_EXCHANGE_EV_SHADOW", True),
        "exchange_ev_production": _env_bool("HIBS_EXCHANGE_EV_PRODUCTION", False),
    }


def exchange_ev_shadow_enabled(paper_cfg: dict[str, Any] | None = None) -> bool:
    return bool(exchange_runtime_config(paper_cfg)["exchange_ev_shadow"])


def exchange_ev_production_enabled(paper_cfg: dict[str, Any] | None = None) -> bool:
    return bool(exchange_runtime_config(paper_cfg)["exchange_ev_production"])
