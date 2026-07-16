from __future__ import annotations

from pathlib import Path
from typing import Any

from hibs_racing.features.store import connect
from hibs_racing.models.win_engine_config import (
    CALIBRATION_CALIBRATED,
    CALIBRATION_UNCALIBRATED,
    min_win_calibration_n,
    win_brier_pass_max,
)
from hibs_racing.models.win_engine_store import (
    ensure_win_engine_schema,
    load_calibration_state,
    update_calibration_state,
)


def _rolling_win_brier(conn, *, race_window: int) -> dict[str, Any]:
    """Mean per-runner Brier over the last N distinct settled races."""
    rows = conn.execute(
        """
        SELECT w.runner_id, w.race_id, w.true_probability, w.brier_score, w.timestamp
        FROM win_engine_predictions w
        WHERE w.brier_score IS NOT NULL
        ORDER BY w.timestamp DESC
        """
    ).fetchall()
    if not rows:
        return {"rolling_brier": None, "sample_n": 0, "races_in_window": 0}

    seen_races: list[str] = []
    brier_vals: list[float] = []
    for row in rows:
        race_id = row["race_id"]
        if race_id not in seen_races:
            seen_races.append(race_id)
        if len(seen_races) > race_window:
            break
        if row["brier_score"] is not None:
            brier_vals.append(float(row["brier_score"]))

    n = len(brier_vals)
    if not n:
        return {"rolling_brier": None, "sample_n": 0, "races_in_window": len(seen_races)}

    return {
        "rolling_brier": sum(brier_vals) / n,
        "sample_n": n,
        "races_in_window": min(len(seen_races), race_window),
    }


def update_brier_on_result(
    conn,
    *,
    race_id: str,
    outcomes: dict[str, int],
) -> None:
    """
    outcomes: runner_id -> finish_pos (1 = winner).
    Per-runner brier = (true_probability - won)^2 where won in {0,1}.
    """
    preds = conn.execute(
        "SELECT runner_id, true_probability FROM win_engine_predictions WHERE race_id = ?",
        (race_id,),
    ).fetchall()
    for pred in preds:
        rid = pred["runner_id"]
        if rid not in outcomes:
            continue
        won = 1.0 if int(outcomes[rid]) == 1 else 0.0
        prob = float(pred["true_probability"])
        brier = (prob - won) ** 2
        conn.execute(
            "UPDATE win_engine_predictions SET brier_score = ? WHERE runner_id = ?",
            (brier, rid),
        )


def sync_brier_from_runners(database: Path) -> int:
    """Backfill brier_score from ingested runners.finish_pos."""
    ensure_win_engine_schema(database)
    updated = 0
    with connect(database) as conn:
        rows = conn.execute(
            """
            SELECT w.runner_id, w.race_id, w.true_probability, r.finish_pos
            FROM win_engine_predictions w
            JOIN runners r ON r.runner_id = w.runner_id
            WHERE r.finish_pos IS NOT NULL
              AND w.brier_score IS NULL
            """
        ).fetchall()
        for row in rows:
            won = 1.0 if int(row["finish_pos"]) == 1 else 0.0
            prob = float(row["true_probability"])
            brier = (prob - won) ** 2
            conn.execute(
                "UPDATE win_engine_predictions SET brier_score = ? WHERE runner_id = ?",
                (brier, row["runner_id"]),
            )
            updated += 1
    return updated


def run_win_engine_sandbox() -> dict[str, Any]:
    """Silent background pass — never raises; safe for cron after refresh-cards."""
    try:
        from hibs_racing.cards.query import load_scored_cards
        from hibs_racing.config import db_path, load_config
        from hibs_racing.models.win_engine_service import run_win_engine

        db = db_path(load_config())
        cards = load_scored_cards(sanitize=False)
        n = 0
        if cards is not None and not cards.empty:
            out = run_win_engine(cards, database=db, persist=True)
            n = len(out) if out is not None else 0
        sync_brier_from_runners(db)
        cal = evaluate_calibration_circuit(db)
        return {"ok": True, "predictions": n, **cal}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def evaluate_calibration_circuit(database: Path) -> dict[str, Any]:
    """Recompute rolling Brier; trip UNCALIBRATED when above threshold."""
    ensure_win_engine_schema(database)
    window = min_win_calibration_n()
    threshold = win_brier_pass_max()

    with connect(database) as conn:
        stats = _rolling_win_brier(conn, race_window=window)
        n = int(stats["sample_n"])
        rolling = stats["rolling_brier"]
        races = int(stats["races_in_window"])

        if n < window:
            state = CALIBRATION_UNCALIBRATED
        elif rolling is not None and rolling > threshold:
            state = CALIBRATION_UNCALIBRATED
        else:
            state = CALIBRATION_CALIBRATED

        update_calibration_state(
            conn,
            calibration_state=state,
            rolling_brier=rolling,
            sample_n=n,
            races_in_window=races,
        )
        return {
            "calibration_state": state,
            "rolling_brier": rolling,
            "sample_n": n,
            "races_in_window": races,
            "threshold": threshold,
            "window": window,
        }


def on_race_results_ingested(
    database: Path,
    *,
    race_id: str,
    outcomes: dict[str, int],
) -> dict[str, Any]:
    """Hook after result ingestion — update Brier scores and evaluate circuit."""
    ensure_win_engine_schema(database)
    with connect(database) as conn:
        update_brier_on_result(conn, race_id=race_id, outcomes=outcomes)
    return evaluate_calibration_circuit(database)


def public_release_allowed(database: Path) -> bool:
    from hibs_racing.models.win_engine_config import win_engine_active

    if not win_engine_active():
        return False
    ensure_win_engine_schema(database)
    with connect(database) as conn:
        return load_calibration_state(conn).get("calibration_state") == CALIBRATION_CALIBRATED
