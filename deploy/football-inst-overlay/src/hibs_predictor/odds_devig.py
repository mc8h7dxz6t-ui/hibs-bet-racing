"""Bookmaker margin removal — odds-ratio, Shin, and log-odds α helpers."""

from __future__ import annotations

import math
from typing import Any, Dict, Literal, Mapping, Optional

FairMethod = Literal["shin", "or"]


def _valid_odds(raw: Any) -> Optional[float]:
    try:
        o = float(raw)
    except (TypeError, ValueError):
        return None
    return o if o > 1.0 else None


def implied_probs(odds: Mapping[str, Any]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for key, raw in odds.items():
        o = _valid_odds(raw)
        if o is not None:
            out[str(key).lower()] = 1.0 / o
    return out


def odds_ratio_devig_probs(odds: Mapping[str, Any]) -> Dict[str, float]:
    """Normalize raw implied probabilities to sum to 1."""
    impl = implied_probs(odds)
    total = sum(impl.values())
    if total <= 0:
        return {}
    return {k: v / total for k, v in impl.items()}


def shin_devig_probs(odds: Mapping[str, Any], *, iterations: int = 40) -> Dict[str, float]:
    """Shin's method for 1X2-style markets (iterative z)."""
    impl = implied_probs(odds)
    if len(impl) < 2:
        return odds_ratio_devig_probs(odds)
    keys = list(impl.keys())
    p = [impl[k] for k in keys]
    z = 0.0
    for _ in range(max(5, iterations)):
        denom = sum(math.sqrt(max(1e-12, pi * (1.0 - z))) for pi in p)
        if denom <= 0:
            break
        z = max(0.0, min(0.99, (sum(p) - 1.0) / denom))
    out: Dict[str, float] = {}
    for key, pi in zip(keys, p):
        fair = math.sqrt(max(1e-12, pi * (1.0 - z)))
        out[key] = fair
    total = sum(out.values())
    if total <= 0:
        return odds_ratio_devig_probs(odds)
    return {k: v / total for k, v in out.items()}


def fair_probs_from_odds(
    odds: Mapping[str, Any],
    *,
    method: FairMethod = "shin",
) -> Dict[str, float]:
    if method == "or":
        return odds_ratio_devig_probs(odds)
    return shin_devig_probs(odds)


def log_odds_alpha(
    model_prob: float,
    fair_prob: float,
    *,
    eps: float = 1e-9,
) -> Optional[float]:
    """Log-odds residual α = logit(model) - logit(fair)."""
    try:
        mp = float(model_prob)
        fp = float(fair_prob)
    except (TypeError, ValueError):
        return None
    if mp <= 0 or mp >= 1 or fp <= 0 or fp >= 1:
        return None
    return math.log((mp + eps) / (1.0 - mp + eps)) - math.log((fp + eps) / (1.0 - fp + eps))


def blend_probs_toward_anchor(
    model: Mapping[str, float],
    anchor: Mapping[str, float],
    *,
    weight: float = 0.35,
) -> Dict[str, float]:
    """Convex blend of model probs toward anchor (e.g. sharp consensus)."""
    w = max(0.0, min(1.0, float(weight)))
    keys = set(model) | set(anchor)
    out: Dict[str, float] = {}
    for key in keys:
        m = float(model.get(key, 0.0) or 0.0)
        a = float(anchor.get(key, m) or 0.0)
        out[key] = (1.0 - w) * m + w * a
    total = sum(out.values())
    if total > 0:
        out = {k: v / total for k, v in out.items()}
    return out
