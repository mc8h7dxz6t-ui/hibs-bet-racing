"""Harville / Henery place probability models."""

from __future__ import annotations

import os


def _henery_gamma() -> float:
    raw = os.environ.get("HIBS_HENERY_CORRECTION", "").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return 1.0
    if raw in ("1", "true", "yes", "on"):
        try:
            return max(1.0, float(os.environ.get("HIBS_HENERY_GAMMA", "1.10")))
        except ValueError:
            return 1.10
    try:
        g = float(raw)
        return g if g > 0 else 1.0
    except ValueError:
        return 1.0


def _apply_henery_transform(probs: list[float], gamma: float) -> list[float]:
    """Henery (1981) style denominator correction — gamma>1 trims longshot place mass."""
    if gamma <= 1.0 + 1e-9:
        return list(probs)
    out: list[float] = []
    for p in probs:
        denom = max(1e-12, 1.0 - p)
        out.append(p / (denom ** (gamma - 1.0)))
    return out


def _apply_longshot_discount(
    win_probs: list[float],
    *,
    threshold: float = 0.03,
    discount: float = 0.85,
) -> list[float]:
    """Scale down severe longshots before Harville (canonical formula over-places tails)."""
    if discount >= 1.0 or threshold <= 0:
        return list(win_probs)
    total = sum(win_probs)
    if total <= 0:
        return list(win_probs)
    out: list[float] = []
    for p in win_probs:
        implied = p / total
        out.append(p * discount if implied < threshold else p)
    return out


def harville_place_probs(
    win_probs: list[float],
    places: int = 3,
    *,
    longshot_win_prob_threshold: float = 0.03,
    longshot_discount: float = 1.0,
    henery_gamma: float | None = None,
) -> list[float]:
    """
    Harville place probabilities (top-k) from win probabilities.
    Optional Henery correction via henery_gamma or HIBS_HENERY_CORRECTION env.
    """
    if places < 1:
        raise ValueError("places must be >= 1")
    n = len(win_probs)
    places = min(places, n)
    if n == 0:
        return []

    wp = _apply_longshot_discount(
        win_probs,
        threshold=longshot_win_prob_threshold,
        discount=longshot_discount,
    )
    total = sum(wp)
    if total <= 0:
        raise ValueError("win_probs must sum to a positive value")

    gamma = henery_gamma if henery_gamma is not None else _henery_gamma()
    p_raw = [x / total for x in wp]
    p = _apply_henery_transform(p_raw, gamma)
    norm = sum(p)
    if norm <= 0:
        p = p_raw
    else:
        p = [x / norm for x in p]

    place_p = [0.0] * n

    # 1st
    for i in range(n):
        place_p[i] += p[i]

    if places >= 2:
        # 2nd: j wins, i second
        for i in range(n):
            for j in range(n):
                if i == j:
                    continue
                denom = 1.0 - p[j]
                if denom > 1e-12:
                    place_p[i] += p[j] * p[i] / denom

    if places >= 3:
        # 3rd: a wins, b second, i third
        for i in range(n):
            for a in range(n):
                if a == i:
                    continue
                denom_a = 1.0 - p[a]
                if denom_a <= 1e-12:
                    continue
                for b in range(n):
                    if b in (a, i):
                        continue
                    denom_b = 1.0 - p[a] - p[b]
                    if denom_b <= 1e-12:
                        continue
                    p_b_given_a = p[b] / denom_a
                    place_p[i] += p[a] * p_b_given_a * (p[i] / denom_b)

    return [min(1.0, max(0.0, x)) for x in place_p]
