"""Sale-ready gate profile — env overlay for OOS ROI tuning."""

from __future__ import annotations

import os
from typing import Any


def sale_gates_enabled() -> bool:
    return os.environ.get("HIBS_RACING_SALE_GATES", "").strip().lower() in ("1", "true", "yes", "on")


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except ValueError:
        return default


def apply_sale_gate_overrides(paper_cfg: dict[str, Any]) -> dict[str, Any]:
    """Merge sale OOS gate thresholds when HIBS_RACING_SALE_GATES=1."""
    if not sale_gates_enabled():
        return dict(paper_cfg)
    out = dict(paper_cfg)
    out["min_place_ev"] = _env_float("HIBS_RACING_MIN_PLACE_EV", 0.12)
    out["min_combo_bayes_place"] = _env_float("HIBS_RACING_MIN_COMBO_BAYES_PLACE", 0.28)
    out["harville_longshot_win_prob_threshold"] = _env_float(
        "HIBS_RACING_HARVILLE_LONGSHOT_THRESHOLD", 0.03
    )
    out["harville_longshot_discount"] = _env_float("HIBS_RACING_HARVILLE_LONGSHOT_DISCOUNT", 0.85)
    g2 = dict(out.get("gate2") or {})
    g2["min_place_ev_small"] = _env_float("HIBS_RACING_MIN_PLACE_EV_SMALL", 0.10)
    g2["min_place_ev_medium"] = out["min_place_ev"]
    g2["min_place_ev_large"] = _env_float("HIBS_RACING_MIN_PLACE_EV_LARGE", 0.14)
    out["gate2"] = g2
    out["_sale_gates_active"] = True
    return out


def sale_gate_status(paper_cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    from hibs_racing.config import load_config

    cfg = load_config()
    paper = apply_sale_gate_overrides(cfg.get("paper") or {})
    return {
        "enabled": sale_gates_enabled(),
        "min_place_ev": float(paper.get("min_place_ev", 0.05)),
        "min_combo_bayes_place": float(paper.get("min_combo_bayes_place", 0.22)),
        "harville_longshot_discount": float(paper.get("harville_longshot_discount", 1.0)),
        "active": bool(paper.get("_sale_gates_active")),
    }
