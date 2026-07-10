"""Gate profile constants and offline compare helpers."""

from __future__ import annotations

from typing import Any, Dict, List, Set

# World Cup / international friendlies regime — informational F9b cohort only.
REGIME_WC: Set[str] = frozenset({"WORLD_CUP", "INTL_FRIENDLIES"})

_DEFAULT_PROFILES: Dict[str, Dict[str, Any]] = {
    "baseline": {
        "label": "Production baseline",
        "HIBS_SHARPEN_GATES": "0",
        "HIBS_VALUE_EDGE_MARGIN": "0.05",
    },
    "trial_sharpen": {
        "label": "Trial sharpen (VPS engineering A)",
        "HIBS_SHARPEN_GATES": "1",
        "HIBS_VALUE_EDGE_MARGIN": "0.07",
    },
}


def list_gate_profiles() -> List[str]:
    return sorted(_DEFAULT_PROFILES.keys())


def profile_env(profile: str) -> Dict[str, str]:
    row = _DEFAULT_PROFILES.get(profile) or {}
    return {k: str(v) for k, v in row.items() if k.startswith("HIBS_")}


def compare_summary(*, days: int = 90, min_bets: int = 5) -> Dict[str, Any]:
    """Lightweight offline summary — full compare via scripts/compare_gate_profiles.py."""
    out: Dict[str, Any] = {
        "window_days": int(days),
        "min_bets": int(min_bets),
        "profiles": list_gate_profiles(),
        "regime_wc": sorted(REGIME_WC),
        "message": "Run scripts/compare_gate_profiles.py for settled-row A/B.",
    }
    try:
        from hibs_predictor.prediction_log import clv_beat_close_summary

        trial = clv_beat_close_summary(days=days, trial_leagues_only=True)
        wc = clv_beat_close_summary(days=days, regime_wc_only=True)
        out["trial_beat_close"] = trial.get("beat_close_pct")
        out["trial_n"] = trial.get("n_clv_rows")
        out["wc_beat_close"] = wc.get("beat_close_pct")
        out["wc_n"] = wc.get("n_clv_rows")
    except Exception as exc:
        out["error"] = str(exc)[:120]
    return out
