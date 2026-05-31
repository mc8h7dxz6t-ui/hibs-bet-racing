from __future__ import annotations


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
) -> list[float]:
    """
    Harville place probabilities (top-k) from win probabilities.
    Phase B starter — swap for Henery calibration once backtest justifies it.
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

    p = [x / total for x in wp]
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
