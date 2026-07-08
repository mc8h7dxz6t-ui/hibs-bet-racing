"""Reliability bins — win + place calibration from paper ledger and snapshots."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


def win_reliability_bins(
    rows: List[Dict[str, Any]],
    *,
    bins: int = 10,
    prob_field: str = "model_win_prob",
    won_field: str = "won",
) -> List[Dict[str, Any]]:
    """Reliability table: predicted win prob vs realised win rate per bin."""
    buckets: List[Dict[str, Any]] = [
        {"bin_lo": i / bins, "bin_hi": (i + 1) / bins, "n": 0, "pred_sum": 0.0, "wins": 0}
        for i in range(bins)
    ]
    for row in rows:
        try:
            prob = float(row.get(prob_field))
        except (TypeError, ValueError):
            continue
        if prob <= 0 or prob > 1:
            continue
        won = bool(row.get(won_field))
        idx = min(int(prob * bins), bins - 1)
        b = buckets[idx]
        b["n"] += 1
        b["pred_sum"] += prob
        if won:
            b["wins"] += 1
    out: List[Dict[str, Any]] = []
    for b in buckets:
        if b["n"] == 0:
            continue
        out.append(
            {
                "bin": f"{b['bin_lo']:.0%}-{b['bin_hi']:.0%}",
                "n": b["n"],
                "avg_predicted_pct": round(100.0 * b["pred_sum"] / b["n"], 2),
                "actual_win_pct": round(100.0 * b["wins"] / b["n"], 2),
            }
        )
    return out


def place_reliability_bins(
    pairs: Sequence[tuple[float, int]],
    *,
    n_bins: int = 10,
    min_bin_n: int = 5,
) -> dict[str, Any]:
    """Bin place predicted probabilities vs binary place hits."""
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


# Backward-compatible alias
reliability_bins = place_reliability_bins


def brier_score_win(rows: List[Dict[str, Any]], *, prob_field: str = "model_win_prob") -> Optional[float]:
    """Binary Brier on win probability vs won outcome."""
    usable = []
    for row in rows:
        try:
            prob = float(row.get(prob_field))
            won = 1.0 if row.get("won") else 0.0
        except (TypeError, ValueError):
            continue
        if prob <= 0 or prob > 1:
            continue
        usable.append((prob, won))
    if not usable:
        return None
    return round(sum((p - y) ** 2 for p, y in usable) / len(usable), 4)


def settled_paper_calibration(
    database: Path,
    *,
    days: int = 180,
    bins: int = 10,
) -> Dict[str, Any]:
    """Load settled paper bets joined to model_win_prob for /api/health."""
    from datetime import datetime, timedelta, timezone

    from hibs_racing.features.store import connect, init_db

    init_db(database)
    since = (datetime.now(timezone.utc).date() - timedelta(days=max(1, days))).isoformat()
    rows: List[Dict[str, Any]] = []
    try:
        with connect(database) as conn:
            cur = conn.execute(
                """
                SELECT
                    pb.runner_id,
                    pb.bet_type,
                    pb.finish_pos,
                    c.model_win_prob
                FROM paper_bets pb
                LEFT JOIN card_scores c ON c.runner_id = pb.runner_id
                WHERE pb.status != 'open'
                  AND pb.bet_type IN ('win', 'each_way')
                  AND pb.created_at >= ?
                  AND c.model_win_prob IS NOT NULL
                  AND c.model_win_prob > 0
                  AND c.model_win_prob <= 1
                """,
                (since,),
            )
            for runner_id, bet_type, finish_pos, model_win_prob in cur.fetchall():
                try:
                    pos = int(finish_pos) if finish_pos is not None else None
                except (TypeError, ValueError):
                    pos = None
                rows.append(
                    {
                        "runner_id": runner_id,
                        "bet_type": bet_type,
                        "model_win_prob": float(model_win_prob),
                        "won": pos == 1,
                    }
                )
    except Exception as exc:
        return {"available": False, "error": str(exc)[:120], "n": 0}

    if not rows:
        return {
            "available": False,
            "n": 0,
            "since": since,
            "message": "No settled paper rows with model_win_prob",
        }
    return {
        "available": True,
        "n": len(rows),
        "since": since,
        "brier_score": brier_score_win(rows),
        "bins": win_reliability_bins(rows, bins=bins),
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
    payload = place_reliability_bins(pairs, n_bins=n_bins)
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
    payload = place_reliability_bins(pairs, n_bins=n_bins)
    payload["source"] = "paper_bets+snapshots"
    payload["days"] = days
    payload["backtest"] = backtest
    return payload
