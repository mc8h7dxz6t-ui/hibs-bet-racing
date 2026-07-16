from __future__ import annotations

from pathlib import Path
from typing import Any

from hibs_racing.features.store import connect
from hibs_racing.models.win_engine_circuit import evaluate_calibration_circuit, public_release_allowed
from hibs_racing.models.win_engine_store import ensure_win_engine_schema, load_predictions_for_date


def _fmt_pct(prob: float | None) -> str | None:
    if prob is None:
        return None
    return f"{100.0 * float(prob):.1f}%"


def build_runner_insights(
    db: Path,
    card_date: str,
    *,
    runner_ids: set[str] | None = None,
) -> dict[str, Any] | None:
    """Return per-runner dual-insight map for frontend when release is allowed."""
    if not public_release_allowed(db):
        return None

    ensure_win_engine_schema(db)
    with connect(db) as conn:
        preds = load_predictions_for_date(conn, card_date)

    insights: dict[str, dict[str, Any]] = {}
    for row in preds:
        rid = row.get("runner_id")
        if not rid:
            continue
        if runner_ids is not None and rid not in runner_ids:
            continue
        live = row.get("live_odds_decimal")
        fair = row.get("fair_odds")
        win_edge = None
        if live and fair and float(live) > 0:
            win_edge = round(float(fair) - float(live), 2)
        insights[rid] = {
            "runner_id": rid,
            "selection": row.get("horse_name"),
            "event": " ".join(p for p in (row.get("course"), row.get("off_time")) if p),
            "live_odds": live,
            "fair_odds": fair,
            "win_value_label": (
                f"{float(live):.2f} vs {float(fair):.2f}" if live and fair else None
            ),
            "win_edge_decimal": win_edge,
            "place_probability": row.get("place_probability"),
            "place_value_label": _fmt_pct(row.get("place_probability")),
            "true_probability": row.get("true_probability"),
        }
    return insights


def attach_win_engine_to_combinations(payload: dict[str, Any], db: Path) -> dict[str, Any]:
    """Augment combinations API payload when calibrated + active."""
    if not public_release_allowed(db):
        return payload

    card_date = payload.get("card_date")
    if not card_date:
        return payload

    runner_ids: set[str] = set()
    for combo in payload.get("combinations") or []:
        for leg in combo.get("legs") or []:
            if leg.get("runner_id"):
                runner_ids.add(str(leg["runner_id"]))
    for leg in payload.get("singles") or []:
        if leg.get("runner_id"):
            runner_ids.add(str(leg["runner_id"]))

    insights = build_runner_insights(db, card_date, runner_ids=runner_ids or None)
    if not insights:
        return payload

    with connect(db) as conn:
        from hibs_racing.models.win_engine_store import load_calibration_state

        cal = load_calibration_state(conn)

    payload = dict(payload)
    payload["win_engine"] = {
        "active": True,
        "calibrated": True,
        "calibration_state": cal.get("calibration_state"),
        "rolling_brier": cal.get("rolling_brier"),
        "insights": insights,
    }
    return payload
