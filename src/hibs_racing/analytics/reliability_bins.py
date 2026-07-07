"""Reliability (calibration) bins for place probabilities."""

from __future__ import annotations

from typing import Any, Iterable, Sequence


def reliability_bins(
    pairs: Sequence[tuple[float, int]],
    *,
    n_bins: int = 10,
    min_bin_n: int = 5,
) -> dict[str, Any]:
    """
    Bin predicted probabilities vs binary outcomes.

    pairs: (predicted_prob, hit) where hit is 0 or 1.
    """
    clean: list[tuple[float, int]] = []
    for pred, hit in pairs:
        try:
            p = float(pred)
            h = int(hit)
        except (TypeError, ValueError):
            continue
        if p < 0 or p > 1 or h not in (0, 1):
            continue
        clean.append((p, h))
    if not clean:
        return {
            "n": 0,
            "n_bins": n_bins,
            "bins": [],
            "mean_calibration_error": None,
            "brier": None,
        }

    n_bins = max(2, min(20, int(n_bins)))
    width = 1.0 / n_bins
    buckets: list[dict[str, Any]] = [
        {"bin": i, "lo": round(i * width, 4), "hi": round((i + 1) * width, 4), "n": 0, "hits": 0, "pred_sum": 0.0}
        for i in range(n_bins)
    ]
    brier_sum = 0.0
    for pred, hit in clean:
        idx = min(n_bins - 1, int(pred / width) if pred < 1.0 else n_bins - 1)
        b = buckets[idx]
        b["n"] += 1
        b["hits"] += hit
        b["pred_sum"] += pred
        brier_sum += (pred - hit) ** 2

    out_bins: list[dict[str, Any]] = []
    mce_terms: list[float] = []
    for b in buckets:
        n = int(b["n"])
        if n < min_bin_n:
            out_bins.append(
                {
                    "bin": b["bin"],
                    "range": [b["lo"], b["hi"]],
                    "n": n,
                    "mean_predicted": round(b["pred_sum"] / n, 4) if n else None,
                    "observed_rate": round(b["hits"] / n, 4) if n else None,
                    "thin": True,
                }
            )
            continue
        mean_p = b["pred_sum"] / n
        obs = b["hits"] / n
        mce_terms.append(abs(mean_p - obs))
        out_bins.append(
            {
                "bin": b["bin"],
                "range": [b["lo"], b["hi"]],
                "n": n,
                "mean_predicted": round(mean_p, 4),
                "observed_rate": round(obs, 4),
                "gap": round(obs - mean_p, 4),
                "thin": False,
            }
        )

    n_all = len(clean)
    return {
        "n": n_all,
        "n_bins": n_bins,
        "bins": out_bins,
        "mean_calibration_error": round(sum(mce_terms) / len(mce_terms), 4) if mce_terms else None,
        "brier": round(brier_sum / n_all, 5),
    }


def place_reliability_from_snapshots(
    conn: Any,
    *,
    days: int = 60,
    n_bins: int = 10,
) -> dict[str, Any]:
    """Calibration from scored_runner_snapshots with finish_pos populated."""
    rows = conn.execute(
        """
        SELECT model_place_prob, finish_pos, places
        FROM scored_runner_snapshots
        WHERE finish_pos IS NOT NULL
          AND model_place_prob IS NOT NULL
          AND card_date >= date('now', ?)
        """,
        (f"-{max(7, int(days))} days",),
    ).fetchall()
    pairs: list[tuple[float, int]] = []
    for prob, finish_pos, places in rows:
        try:
            p = float(prob)
            pos = int(finish_pos)
            k = int(places or 3)
        except (TypeError, ValueError):
            continue
        if p <= 0 or p > 1 or pos <= 0:
            continue
        pairs.append((p, 1 if pos <= max(1, k) else 0))
    payload = reliability_bins(pairs, n_bins=n_bins)
    payload["source"] = "scored_runner_snapshots"
    payload["days"] = days
    return payload


def place_reliability_from_ledger(
    conn: Any,
    *,
    days: int = 60,
    n_bins: int = 10,
    backtest: bool = False,
) -> dict[str, Any]:
    """Join settled paper bets to snapshots for place-prob calibration."""
    rows = conn.execute(
        """
        SELECT s.model_place_prob, pb.finish_pos, s.places
        FROM paper_bets pb
        JOIN scored_runner_snapshots s
          ON s.runner_id = pb.runner_id AND s.race_id = pb.race_id
        WHERE pb.status != 'open'
          AND pb.finish_pos IS NOT NULL
          AND s.model_place_prob IS NOT NULL
          AND pb.backtest = ?
          AND pb.created_at >= datetime('now', ?)
        """,
        (1 if backtest else 0, f"-{max(7, int(days))} days"),
    ).fetchall()
    pairs: list[tuple[float, int]] = []
    for prob, finish_pos, places in rows:
        try:
            p = float(prob)
            pos = int(finish_pos)
            k = int(places or 3)
        except (TypeError, ValueError):
            continue
        pairs.append((p, 1 if pos <= max(1, k) else 0))
    payload = reliability_bins(pairs, n_bins=n_bins)
    payload["source"] = "paper_bets+snapshots"
    payload["days"] = days
    payload["backtest"] = backtest
    return payload
