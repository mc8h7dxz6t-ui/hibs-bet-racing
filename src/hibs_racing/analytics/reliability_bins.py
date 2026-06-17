"""Win-probability reliability bins from settled paper ledger (additive analytics)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional


def reliability_bins(
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
                WHERE pb.status = 'settled'
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
        "bins": reliability_bins(rows, bins=bins),
    }
