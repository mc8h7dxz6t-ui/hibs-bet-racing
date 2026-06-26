"""Population Stability Index (PSI) and Kolmogorov–Smirnov drift statistics."""

from __future__ import annotations

import math
from typing import Sequence


def _histogram_bins(
    baseline: Sequence[float],
    current: Sequence[float],
    *,
    bins: int = 10,
) -> tuple[list[float], list[float], list[float]]:
    """Shared bin edges from baseline quantiles; returns baseline%, current%, edges."""
    if bins < 2:
        raise ValueError("bins must be >= 2")
    if not baseline:
        raise ValueError("baseline must not be empty")
    if not current:
        raise ValueError("current must not be empty")

    sorted_base = sorted(float(x) for x in baseline)
    n = len(sorted_base)
    edges: list[float] = []
    for i in range(1, bins):
        idx = min(n - 1, int(i * n / bins))
        edges.append(sorted_base[idx])
    lo = sorted_base[0]
    hi = sorted_base[-1]
    if lo == hi:
        edges = [lo - 1e-9, hi + 1e-9]
    else:
        edges = [lo - 1e-9] + edges + [hi + 1e-9]

    def _counts(values: Sequence[float]) -> list[float]:
        counts = [0] * (len(edges) - 1)
        for v in values:
            x = float(v)
            placed = False
            for i in range(len(edges) - 2):
                if edges[i] <= x < edges[i + 1]:
                    counts[i] += 1
                    placed = True
                    break
            if not placed:
                counts[-1] += 1
        total = float(len(values)) or 1.0
        return [c / total for c in counts]

    return _counts(baseline), _counts(current), edges


def compute_psi(
    baseline: Sequence[float],
    current: Sequence[float],
    *,
    bins: int = 10,
    epsilon: float = 1e-6,
) -> float:
    """
    PSI = sum((actual% - expected%) * ln(actual% / expected%)).
    Industry bands: <0.1 stable, 0.1–0.25 watch, >0.25 significant drift.
    """
    base_pct, cur_pct, _ = _histogram_bins(baseline, current, bins=bins)
    psi = 0.0
    for e, a in zip(base_pct, cur_pct, strict=True):
        e = max(e, epsilon)
        a = max(a, epsilon)
        psi += (a - e) * math.log(a / e)
    return psi


def compute_ks_statistic(baseline: Sequence[float], current: Sequence[float]) -> float:
    """Two-sample KS D statistic — max |F1(x) - F2(x)|."""
    base = sorted(float(x) for x in baseline)
    cur = sorted(float(x) for x in current)
    if not base or not cur:
        return 0.0
    all_vals = sorted(set(base + cur))
    n1 = len(base)
    n2 = len(cur)
    i1 = i2 = 0
    cdf1 = cdf2 = 0.0
    d_max = 0.0
    for x in all_vals:
        while i1 < n1 and base[i1] <= x:
            i1 += 1
        while i2 < n2 and cur[i2] <= x:
            i2 += 1
        cdf1 = i1 / n1
        cdf2 = i2 / n2
        d_max = max(d_max, abs(cdf1 - cdf2))
    return d_max


def ks_critical_value(alpha: float = 0.05) -> float:
    """Approximate KS critical value for large samples (D_alpha ~ sqrt(-ln(alpha/2)*0.5))."""
    return math.sqrt(-0.5 * math.log(alpha / 2.0))


def psi_band(psi: float) -> str:
    if psi < 0.1:
        return "stable"
    if psi < 0.25:
        return "watch"
    return "significant"
