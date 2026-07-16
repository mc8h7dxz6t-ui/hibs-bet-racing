from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from hibs_racing.features.store import connect
from hibs_racing.models.win_engine_config import (
    CALIBRATION_CALIBRATED,
    CALIBRATION_UNCALIBRATED,
    max_brier_for_field_size,
    min_market_beat_bps,
    min_win_calibration_n,
)
from hibs_racing.models.win_engine_store import (
    ensure_win_engine_schema,
    load_calibration_state,
    update_calibration_state,
)


def multiclass_field_brier(probabilities: list[float], outcomes: list[int]) -> float:
    """BS_R = sum((p_i - y_i)^2) across the full race field."""
    if len(probabilities) != len(outcomes) or not probabilities:
        return float("nan")
    return sum((float(p) - float(y)) ** 2 for p, y in zip(probabilities, outcomes))


def devig_exchange_probabilities(odds: list[float]) -> list[float] | None:
    """
    Power-ratio de-vig: find exponent alpha so sum((1/odds_i)^alpha) == 1.
    Falls back to proportional normalization when the field is under-rounded.
    """
    if not odds:
        return None
    raw: list[float] = []
    for o in odds:
        try:
            dec = float(o)
        except (TypeError, ValueError):
            return None
        if dec <= 1.0 or not math.isfinite(dec):
            return None
        raw.append(1.0 / dec)

    total = sum(raw)
    if total <= 0.0:
        return None
    if total <= 1.0 + 1e-9:
        return [r / total for r in raw]

    lo, hi = 0.0, 1.0
    for _ in range(64):
        mid = (lo + hi) / 2.0
        powered_sum = sum(r**mid for r in raw)
        if powered_sum > 1.0:
            lo = mid
        else:
            hi = mid
    alpha = (lo + hi) / 2.0
    powered = [r**alpha for r in raw]
    norm = sum(powered)
    if norm <= 0.0:
        return None
    return [p / norm for p in powered]


def market_beat_passes(*, model_brier: float, market_brier: float, min_beat_bps: int) -> bool:
    if not math.isfinite(model_brier) or not math.isfinite(market_brier) or market_brier <= 0.0:
        return False
    margin = min_beat_bps / 10_000.0
    return model_brier <= market_brier * (1.0 - margin)


def exchange_beat_delta_bps(*, model_brier: float, market_brier: float) -> float | None:
    if not math.isfinite(model_brier) or not math.isfinite(market_brier) or market_brier <= 0.0:
        return None
    return ((market_brier - model_brier) / market_brier) * 10_000.0


def _race_blocks_from_rows(rows: list[Any]) -> dict[str, list[dict[str, Any]]]:
    blocks: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        race_id = row["race_id"]
        blocks.setdefault(race_id, []).append(dict(row))
    return blocks


def _outcome_from_row(row: dict[str, Any]) -> int | None:
    if row.get("won") is not None:
        return int(row["won"])
    if row.get("finish_pos") is not None:
        return 1 if int(row["finish_pos"]) == 1 else 0
    if row.get("brier_score") is not None and row.get("true_probability") is not None:
        prob = float(row["true_probability"])
        brier = float(row["brier_score"])
        if abs(brier - (prob - 1.0) ** 2) < 1e-6:
            return 1
        if abs(brier - prob**2) < 1e-6:
            return 0
    return None


def evaluate_race_field_block(
    runners: list[dict[str, Any]],
    *,
    min_beat_bps: int | None = None,
) -> dict[str, Any]:
    """
    Validate a single race_id block: multiclass field Brier, variable bounds, market beat.
    """
    min_beat_bps = min_market_beat_bps() if min_beat_bps is None else min_beat_bps
    field_size = len(runners)
    probs: list[float] = []
    outcomes: list[int] = []
    odds: list[float] = []

    for runner in runners:
        outcome = _outcome_from_row(runner)
        if outcome is None:
            return {
                "race_id": runners[0].get("race_id"),
                "field_size": field_size,
                "valid": False,
                "reason": "missing_outcome",
            }
        probs.append(float(runner["true_probability"]))
        outcomes.append(outcome)
        mb = runner.get("matchbook_back_odds")
        if mb is None or (isinstance(mb, float) and math.isnan(mb)):
            mb = runner.get("live_odds_decimal")
        odds.append(float(mb) if mb is not None else float("nan"))

    model_brier = multiclass_field_brier(probs, outcomes)
    cap = max_brier_for_field_size(field_size)
    bounds_pass = math.isfinite(model_brier) and model_brier <= cap

    devig_probs = None
    market_brier: float | None = None
    market_pass = False
    beat_bps: float | None = None

    if all(math.isfinite(o) and o > 1.0 for o in odds):
        devig_probs = devig_exchange_probabilities(odds)
        if devig_probs is not None:
            market_brier = multiclass_field_brier(devig_probs, outcomes)
            market_pass = market_beat_passes(
                model_brier=model_brier,
                market_brier=market_brier,
                min_beat_bps=min_beat_bps,
            )
            beat_bps = exchange_beat_delta_bps(model_brier=model_brier, market_brier=market_brier)

    return {
        "race_id": runners[0].get("race_id"),
        "field_size": field_size,
        "model_brier": model_brier,
        "market_brier": market_brier,
        "max_brier_cap": cap,
        "bounds_pass": bounds_pass,
        "market_pass": market_pass,
        "exchange_beat_delta_bps": beat_bps,
        "valid": True,
        "block_pass": bounds_pass and market_pass,
    }


def _load_settled_race_rows(conn, *, race_window: int) -> list[dict[str, Any]]:
    """Most recent settled races with outcomes, capped at race_window distinct race_ids."""
    rows = conn.execute(
        """
        SELECT
            w.runner_id,
            w.race_id,
            w.true_probability,
            w.brier_score,
            w.live_odds_decimal,
            w.matchbook_back_odds,
            w.race_field_brier,
            w.market_race_brier,
            w.field_size,
            w.timestamp,
            r.finish_pos
        FROM win_engine_predictions w
        LEFT JOIN runners r ON r.runner_id = w.runner_id
        WHERE w.brier_score IS NOT NULL OR r.finish_pos IS NOT NULL
        ORDER BY w.timestamp DESC
        """
    ).fetchall()
    if not rows:
        return []

    blocks = _race_blocks_from_rows(rows)
    ordered_race_ids: list[str] = []
    seen: set[str] = set()
    for row in rows:
        race_id = row["race_id"]
        if race_id in seen:
            continue
        seen.add(race_id)
        ordered_race_ids.append(race_id)
        if len(ordered_race_ids) >= race_window:
            break

    settled: list[dict[str, Any]] = []
    for race_id in ordered_race_ids:
        block = blocks[race_id]
        if all(_outcome_from_row(r) is not None for r in block):
            settled.extend(block)
    return settled


def _rolling_field_calibration(conn, *, race_window: int) -> dict[str, Any]:
    settled_rows = _load_settled_race_rows(conn, race_window=race_window)
    if not settled_rows:
        return {
            "rolling_brier": None,
            "market_brier_rolling": None,
            "exchange_beat_delta_bps": None,
            "sample_n": 0,
            "races_in_window": 0,
            "variable_bounds_pass": False,
            "market_beat_pass": False,
            "failed_races": [],
        }

    blocks = _race_blocks_from_rows(settled_rows)
    race_ids = list(dict.fromkeys(r["race_id"] for r in settled_rows))
    race_evals: list[dict[str, Any]] = []
    failed_races: list[str] = []
    model_briers: list[float] = []
    market_briers: list[float] = []
    beat_deltas: list[float] = []

    for race_id in race_ids:
        evaluation = evaluate_race_field_block(blocks[race_id])
        if not evaluation.get("valid"):
            failed_races.append(race_id)
            continue
        race_evals.append(evaluation)
        model_b = float(evaluation["model_brier"])
        model_briers.append(model_b)
        if evaluation.get("market_brier") is not None:
            market_briers.append(float(evaluation["market_brier"]))
        if evaluation.get("exchange_beat_delta_bps") is not None:
            beat_deltas.append(float(evaluation["exchange_beat_delta_bps"]))
        if not evaluation.get("block_pass"):
            failed_races.append(race_id)

    n_races = len(race_evals)
    rolling = sum(model_briers) / n_races if model_briers else None
    market_rolling = sum(market_briers) / len(market_briers) if market_briers else None
    mean_beat_bps = sum(beat_deltas) / len(beat_deltas) if beat_deltas else None

    bounds_pass = n_races > 0 and all(e.get("bounds_pass") for e in race_evals)
    market_pass = n_races > 0 and all(e.get("market_pass") for e in race_evals)

    return {
        "rolling_brier": rolling,
        "market_brier_rolling": market_rolling,
        "exchange_beat_delta_bps": mean_beat_bps,
        "sample_n": n_races,
        "races_in_window": n_races,
        "variable_bounds_pass": bounds_pass,
        "market_beat_pass": market_pass,
        "failed_races": failed_races,
        "race_evaluations": race_evals,
    }


def _persist_race_field_metrics(
    conn,
    *,
    race_id: str,
    model_brier: float,
    market_brier: float | None,
    field_size: int,
) -> None:
    conn.execute(
        """
        UPDATE win_engine_predictions
        SET race_field_brier = ?,
            market_race_brier = ?,
            field_size = ?
        WHERE race_id = ?
        """,
        (model_brier, market_brier, field_size, race_id),
    )


def update_brier_on_result(
    conn,
    *,
    race_id: str,
    outcomes: dict[str, int],
) -> None:
    """
    outcomes: runner_id -> finish_pos (1 = winner).
    Computes multiclass field Brier per race and per-runner binary components.
    """
    preds = conn.execute(
        """
        SELECT runner_id, true_probability, matchbook_back_odds, live_odds_decimal
        FROM win_engine_predictions
        WHERE race_id = ?
        """,
        (race_id,),
    ).fetchall()
    if not preds:
        return

    runners: list[dict[str, Any]] = []
    for pred in preds:
        rid = pred["runner_id"]
        if rid not in outcomes:
            continue
        won = 1 if int(outcomes[rid]) == 1 else 0
        runners.append(
            {
                "runner_id": rid,
                "race_id": race_id,
                "true_probability": float(pred["true_probability"]),
                "matchbook_back_odds": pred["matchbook_back_odds"],
                "live_odds_decimal": pred["live_odds_decimal"],
                "won": won,
            }
        )

    if not runners:
        return

    evaluation = evaluate_race_field_block(runners)
    model_brier = float(evaluation.get("model_brier") or float("nan"))
    market_brier = evaluation.get("market_brier")
    field_size = len(runners)

    for runner in runners:
        rid = runner["runner_id"]
        won = float(runner["won"])
        prob = float(runner["true_probability"])
        brier = (prob - won) ** 2
        conn.execute(
            "UPDATE win_engine_predictions SET brier_score = ? WHERE runner_id = ?",
            (brier, rid),
        )

    if math.isfinite(model_brier):
        _persist_race_field_metrics(
            conn,
            race_id=race_id,
            model_brier=model_brier,
            market_brier=float(market_brier) if market_brier is not None else None,
            field_size=field_size,
        )


def sync_brier_from_runners(database: Path) -> int:
    """Backfill per-runner and per-race field Brier from ingested runners.finish_pos."""
    ensure_win_engine_schema(database)
    updated = 0
    with connect(database) as conn:
        race_ids = conn.execute(
            """
            SELECT DISTINCT w.race_id
            FROM win_engine_predictions w
            JOIN runners r ON r.runner_id = w.runner_id
            WHERE r.finish_pos IS NOT NULL
              AND (w.brier_score IS NULL OR w.race_field_brier IS NULL)
            """
        ).fetchall()
        for row in race_ids:
            race_id = row["race_id"]
            outcomes_rows = conn.execute(
                """
                SELECT w.runner_id, r.finish_pos
                FROM win_engine_predictions w
                JOIN runners r ON r.runner_id = w.runner_id
                WHERE w.race_id = ? AND r.finish_pos IS NOT NULL
                """,
                (race_id,),
            ).fetchall()
            outcomes = {r["runner_id"]: int(r["finish_pos"]) for r in outcomes_rows}
            if outcomes:
                update_brier_on_result(conn, race_id=race_id, outcomes=outcomes)
                updated += len(outcomes)
    return updated


def run_win_engine_sandbox() -> dict[str, Any]:
    """Silent background pass — never raises; safe for cron after refresh-cards."""
    try:
        from hibs_racing.cards.query import load_scored_cards
        from hibs_racing.config import db_path, load_config
        from hibs_racing.models.win_engine_service import run_win_engine_calibration_circuit

        db = db_path(load_config())
        cards = load_scored_cards(sanitize=False)
        n = 0
        if cards is not None and not cards.empty:
            from hibs_racing.models.win_engine_service import run_win_engine

            out = run_win_engine(cards, database=db, persist=True)
            n = len(out) if out is not None else 0
        sync_brier_from_runners(db)
        cal = run_win_engine_calibration_circuit(db)
        return {"ok": True, "predictions": n, **cal}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def evaluate_calibration_circuit(database: Path) -> dict[str, Any]:
    """Recompute rolling field calibration; trip UNCALIBRATED on any contract failure."""
    from hibs_racing.models.win_engine_service import run_win_engine_calibration_circuit

    return run_win_engine_calibration_circuit(database)


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


def apply_calibration_circuit_breaker(database: Path) -> dict[str, Any]:
    """
    Core circuit evaluation shared by service layer.
    Forces UNCALIBRATED when race count < N or any race block fails contracts.
    """
    ensure_win_engine_schema(database)
    window = min_win_calibration_n()
    min_beat = min_market_beat_bps()

    with connect(database) as conn:
        stats = _rolling_field_calibration(conn, race_window=window)
        n_races = int(stats["races_in_window"])
        rolling = stats["rolling_brier"]
        bounds_pass = bool(stats["variable_bounds_pass"])
        market_pass = bool(stats["market_beat_pass"])
        failed = stats.get("failed_races") or []

        if n_races < window:
            state = CALIBRATION_UNCALIBRATED
        elif failed:
            state = CALIBRATION_UNCALIBRATED
        elif not bounds_pass or not market_pass:
            state = CALIBRATION_UNCALIBRATED
        else:
            state = CALIBRATION_CALIBRATED

        update_calibration_state(
            conn,
            calibration_state=state,
            rolling_brier=rolling,
            sample_n=n_races,
            races_in_window=n_races,
            market_brier_rolling=stats.get("market_brier_rolling"),
            exchange_beat_delta_bps=stats.get("exchange_beat_delta_bps"),
            variable_bounds_pass=bounds_pass and not failed,
            market_beat_pass=market_pass and not failed,
        )

        return {
            "status": "CALIBRATION_CHECK_COMPLETE",
            "calibration_state": state,
            "rolling_brier": rolling,
            "market_brier_rolling": stats.get("market_brier_rolling"),
            "exchange_beat_delta_bps": stats.get("exchange_beat_delta_bps"),
            "sample_n": n_races,
            "races_in_window": n_races,
            "variable_bounds_check": "PASSED" if bounds_pass and not failed else "FAILED",
            "market_beat_check": "PASSED" if market_pass and not failed else "FAILED",
            "min_market_beat_bps": min_beat,
            "window": window,
            "failed_races": failed[:20],
            "global_circuit_breaker": "ARMED_SAFE" if state == CALIBRATION_CALIBRATED else "TRIPPED",
            "action": "LIFTING_API_CLOAK_ALLOWED" if state == CALIBRATION_CALIBRATED else "API_CLOAK_ENFORCED",
        }
