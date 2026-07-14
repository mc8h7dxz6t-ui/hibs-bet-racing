"""Holdout isotonic calibration for per-race win probabilities (before Harville)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from hibs_racing.config import ROOT, db_path, load_config
from hibs_racing.features.store import connect, init_db

DEFAULT_CACHE = ROOT / "data" / "models" / "win_prob_isotonic.json"
MIN_FIT_ROWS = 80
MIN_BIN_ROWS = 5


def calibration_cache_path() -> Path:
    cfg = load_config()
    rel = (cfg.get("ranker") or {}).get("calibration_file", "win_prob_isotonic.json")
    if Path(rel).is_absolute():
        return Path(rel)
    return ROOT / "data" / "models" / rel


def load_calibration_payload() -> dict[str, Any]:
    path = calibration_cache_path()
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_calibration_payload(payload: dict[str, Any]) -> Path:
    path = calibration_cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _fit_isotonic_knots(pairs: list[tuple[float, int]], *, n_bins: int = 12) -> list[dict[str, float]]:
    if len(pairs) < MIN_FIT_ROWS:
        return []
    df = pd.DataFrame(pairs, columns=["pred", "won"])
    df = df[(df["pred"] > 0) & (df["pred"] <= 1)]
    if df.empty:
        return []
    try:
        from sklearn.isotonic import IsotonicRegression

        ir = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
        ir.fit(df["pred"].values, df["won"].values)
        xs = np.linspace(0.02, 0.98, n_bins)
        ys = ir.predict(xs)
        return [{"x": round(float(x), 5), "y": round(float(y), 5)} for x, y in zip(xs, ys)]
    except ImportError:
        # Piecewise bin calibration without sklearn
        knots: list[dict[str, float]] = []
        width = 1.0 / n_bins
        for i in range(n_bins):
            lo, hi = i * width, (i + 1) * width
            chunk = df[(df["pred"] >= lo) & (df["pred"] < hi if i < n_bins - 1 else df["pred"] <= hi)]
            if len(chunk) < MIN_BIN_ROWS:
                continue
            knots.append(
                {
                    "x": round((lo + hi) / 2, 5),
                    "y": round(float(chunk["won"].mean()), 5),
                }
            )
        return knots


def fit_from_settled_paper(*, database: Path | None = None, days: int | None = 365) -> dict[str, Any]:
    """Fit isotonic map from settled forward paper bets joined to model_win_prob."""
    db = database or db_path(load_config())
    init_db(db)
    clause = ""
    params: list[Any] = []
    if days is not None:
        clause = "AND pb.created_at >= date('now', ?)"
        params.append(f"-{int(days)} days")
    with connect(db) as conn:
        rows = conn.execute(
            f"""
            SELECT c.model_win_prob, CASE WHEN pb.status = 'won' THEN 1 ELSE 0 END AS won
            FROM paper_bets pb
            JOIN card_scores c ON c.runner_id = pb.runner_id
            WHERE pb.status IN ('won', 'lost', 'placed')
              AND pb.backtest = 0
              AND pb.is_value_pick = 1
              AND c.model_win_prob IS NOT NULL
              {clause}
            """,
            params,
        ).fetchall()
    pairs = [(float(r[0]), int(r[1])) for r in rows if r[0] is not None]
    knots = _fit_isotonic_knots(pairs)
    brier_before = _brier(pairs)
    calibrated_pairs = [(float(_apply_knots(p, knots)), w) for p, w in pairs] if knots else pairs
    brier_after = _brier(calibrated_pairs) if knots else None
    payload = {
        "fitted_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        .replace(microsecond=0)
        .isoformat(),
        "n_rows": len(pairs),
        "knots": knots,
        "brier_before": round(brier_before, 5) if brier_before is not None else None,
        "brier_after": round(brier_after, 5) if brier_after is not None else None,
        "method": "isotonic" if knots else "none",
    }
    if knots:
        save_calibration_payload(payload)
    return payload


def _brier(pairs: list[tuple[float, int]]) -> float | None:
    if not pairs:
        return None
    err = 0.0
    for p, w in pairs:
        err += (p - w) ** 2
    return err / len(pairs)


def _apply_knots(prob: float, knots: list[dict[str, float]]) -> float:
    if not knots:
        return prob
    xs = [k["x"] for k in knots]
    ys = [k["y"] for k in knots]
    if prob <= xs[0]:
        return ys[0]
    if prob >= xs[-1]:
        return ys[-1]
    for i in range(len(xs) - 1):
        if xs[i] <= prob <= xs[i + 1]:
            span = xs[i + 1] - xs[i]
            if span <= 0:
                return ys[i + 1]
            t = (prob - xs[i]) / span
            return ys[i] + t * (ys[i + 1] - ys[i])
    return prob


def calibration_enabled() -> bool:
    raw = __import__("os").environ.get("HIBS_WIN_PROB_CALIBRATION", "").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    if raw in ("1", "true", "yes", "on"):
        return True
    cfg = load_config()
    return bool((cfg.get("ranker") or {}).get("win_prob_calibration", True))


def apply_win_prob_calibration(frame: pd.DataFrame) -> pd.DataFrame:
    """Per-race isotonic adjust + renormalize so win probs sum to ~1."""
    if not calibration_enabled() or "model_win_prob" not in frame.columns:
        return frame
    payload = load_calibration_payload()
    knots = payload.get("knots") or []
    if not knots:
        return frame
    out = frame.copy()
    calibrated: list[float] = []
    for _, group in out.groupby("race_id", sort=False):
        raw = group["model_win_prob"].astype(float).tolist()
        adj = [_apply_knots(p, knots) for p in raw]
        s = sum(adj)
        if s > 0:
            adj = [p / s for p in adj]
        calibrated.extend(adj)
    out["model_win_prob_raw"] = out["model_win_prob"]
    out["model_win_prob"] = calibrated
    out["win_prob_calibrated"] = 1
    return out
