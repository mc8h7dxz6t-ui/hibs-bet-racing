"""Harville / EW runtime profile — consistent backtest exports and live scoring."""

from __future__ import annotations

import os
from typing import Any

from hibs_racing.config import load_config


def harville_longshot_discount(configured: float) -> float:
    """
    Effective longshot discount applied in score_card Harville pass.

    HIBS_HARVILLE_CORRECTION=0 disables trim; =1 forces config discount (default 0.85).
    """
    raw = os.environ.get("HIBS_HARVILLE_CORRECTION", "").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return 1.0
    if raw in ("1", "true", "yes", "on"):
        return configured if configured < 1.0 else 0.85
    return configured


def harville_runtime_config(cfg: dict | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    from hibs_racing.sale_gates import apply_sale_gate_overrides

    paper = apply_sale_gate_overrides(cfg.get("paper") or {})
    configured = float(paper.get("harville_longshot_discount", 1.0))
    effective = harville_longshot_discount(configured)
    env = os.environ.get("HIBS_HARVILLE_CORRECTION", "").strip() or "default"
    henery_env = os.environ.get("HIBS_HENERY_CORRECTION", "").strip() or "default"
    return {
        "correction_env": env,
        "henery_correction_env": henery_env,
        "win_prob_threshold": float(paper.get("harville_longshot_win_prob_threshold", 0.03)),
        "configured_discount": configured,
        "effective_discount": effective,
        "min_place_ev": float(paper.get("min_place_ev", 0.05)),
        "min_combo_bayes_place": float(paper.get("min_combo_bayes_place", 0.22)),
        "default_place_fraction": float(paper.get("default_place_fraction", 0.25)),
        "default_places": int(paper.get("default_places", 3)),
        "sale_gates": bool(paper.get("_sale_gates_active")),
    }
