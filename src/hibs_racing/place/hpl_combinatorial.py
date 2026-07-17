"""Harville-Plackett-Luce combinatorial place engine with Henery power-law correction."""

from __future__ import annotations

import json
import os
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from hibs_racing.models.win_engine_circuit import devig_exchange_probabilities
from hibs_racing.models.win_engine_config import CALIBRATION_CALIBRATED, win_engine_public_release_allowed
from hibs_racing.models.win_engine_store import ensure_win_engine_schema, load_calibration_state
from hibs_racing.place.place_picker_config import (
    liquidity_floor_gbp,
    min_place_edge_bps,
    place_henery_gamma_base,
)


def _normalize_probabilities(probs: np.ndarray) -> np.ndarray:
    arr = np.asarray(probs, dtype=np.float64)
    arr = np.clip(arr, 1e-12, None)
    total = float(arr.sum())
    if total <= 0.0:
        raise ValueError("win probabilities must sum to a positive value")
    return arr / total


def _power_vector(probs: np.ndarray, gamma: float) -> np.ndarray:
    return np.power(np.clip(probs, 1e-12, 1.0), float(gamma))


def henery_conditional_vector(
    probs: np.ndarray,
    *,
    gamma: float,
    exclude_idx: int,
) -> np.ndarray:
    """
  For every runner j given winner i, enforce:
      (p_j ** gamma) / sum(p_k ** gamma) over k != i
    """
    g = _power_vector(probs, gamma)
    n = len(probs)
    out = np.zeros(n, dtype=np.float64)
    mask = np.ones(n, dtype=bool)
    mask[exclude_idx] = False
    denom = float(g[mask].sum())
    if denom <= 0.0:
        out[mask] = 1.0 / max(1, int(mask.sum()))
        return out
    out[mask] = g[mask] / denom
    return out


def _place_prob_second_vectorized(probs: np.ndarray, gamma: float) -> np.ndarray:
    g = _power_vector(probs, gamma)
    total_g = float(g.sum())
    denoms = total_g - g
    valid = denoms > 1e-12
    contrib = np.zeros((len(probs), len(probs)), dtype=np.float64)
    contrib[valid, :] = (probs[valid, None] * g[None, :]) / denoms[valid, None]
    np.fill_diagonal(contrib, 0.0)
    return contrib.sum(axis=0)


def _place_prob_third_vectorized(probs: np.ndarray, gamma: float) -> np.ndarray:
    n = len(probs)
    g = _power_vector(probs, gamma)
    place3 = np.zeros(n, dtype=np.float64)
    for a in range(n):
        denom_ab = float(g.sum() - g[a])
        if denom_ab <= 1e-12:
            continue
        for b in range(n):
            if b == a:
                continue
            p_ab = probs[a] * (g[b] / denom_ab)
            denom_abc = float(g.sum() - g[a] - g[b])
            if denom_abc <= 1e-12:
                continue
            for c in range(n):
                if c in (a, b):
                    continue
                place3[c] += p_ab * (g[c] / denom_abc)
    return place3


def _place_prob_fourth_vectorized(probs: np.ndarray, gamma: float) -> np.ndarray:
    n = len(probs)
    g = _power_vector(probs, gamma)
    place4 = np.zeros(n, dtype=np.float64)
    for a in range(n):
        denom_a = float(g.sum() - g[a])
        if denom_a <= 1e-12:
            continue
        for b in range(n):
            if b == a:
                continue
            p_ab = probs[a] * (g[b] / denom_a)
            denom_ab = float(g.sum() - g[a] - g[b])
            if denom_ab <= 1e-12:
                continue
            for c in range(n):
                if c in (a, b):
                    continue
                p_abc = p_ab * (g[c] / denom_ab)
                denom_abcd = float(g.sum() - g[a] - g[b] - g[c])
                if denom_abcd <= 1e-12:
                    continue
                for d in range(n):
                    if d in (a, b, c):
                        continue
                    place4[d] += p_abc * (g[d] / denom_abcd)
    return place4


def resolve_place_positions(field_size: int, configured_places: int | None = None) -> int:
    fs = max(1, int(field_size))
    if configured_places is not None and int(configured_places) > 0:
        return min(int(configured_places), fs)
    if fs >= 16:
        return min(4, fs)
    return min(3, fs)


def hpl_place_probabilities(
    win_probs: Sequence[float],
    *,
    places: int,
    gamma: float | None = None,
    field_size: int | None = None,
) -> np.ndarray:
    """
    Vectorized HPL combinatorial place probabilities (top-k) with Henery power-law correction.
    """
    probs = _normalize_probabilities(np.asarray(win_probs, dtype=np.float64))
    n = len(probs)
    fs = int(field_size) if field_size is not None else n
    k = resolve_place_positions(fs, configured_places=places)
    k = min(k, n)
    if k <= 0:
        return np.zeros(n, dtype=np.float64)

    g = place_henery_gamma_base() if gamma is None else float(gamma)
    first = probs.copy()
    place = np.zeros(n, dtype=np.float64)
    place += first
    if k >= 2:
        place += _place_prob_second_vectorized(probs, g)
    if k >= 3:
        place += _place_prob_third_vectorized(probs, g)
    if k >= 4:
        place += _place_prob_fourth_vectorized(probs, g)
    return np.clip(place, 0.0, 1.0)


def institutional_reference_second_place(probs: Sequence[float], runner_idx: int, *, gamma: float) -> float:
    """Closed-form 2nd-place probability for validation against reference charts."""
    p = _normalize_probabilities(np.asarray(probs, dtype=np.float64))
    second = _place_prob_second_vectorized(p, gamma)
    return float(second[int(runner_idx)])


def _win_engine_calibrated(database) -> bool:
    ensure_win_engine_schema(database)
    from hibs_racing.features.store import connect

    with connect(database) as conn:
        state = load_calibration_state(conn)
    return state.get("calibration_state") == CALIBRATION_CALIBRATED


def resolve_race_win_probabilities(group: pd.DataFrame, *, database) -> np.ndarray:
    """
    McFadden win engine when calibrated; else calibrated ranker softmax; else de-vigged exchange backs.
    """
    n = len(group)
    if n == 0:
        return np.array([], dtype=np.float64)

    if (
        win_engine_public_release_allowed()
        and "true_probability" in group.columns
        and group["true_probability"].notna().all()
    ):
        tp = pd.to_numeric(group["true_probability"], errors="coerce").to_numpy(dtype=np.float64)
        if np.isfinite(tp).all() and float(tp.sum()) > 0.0:
            return _normalize_probabilities(tp)

    mwp = pd.to_numeric(group.get("model_win_prob"), errors="coerce").to_numpy(dtype=np.float64)
    if np.isfinite(mwp).all() and float(mwp.sum()) > 0.0:
        return _normalize_probabilities(mwp)

    odds: list[float] = []
    for _, row in group.iterrows():
        raw = row.get("matchbook_back_odds")
        if raw is None or (isinstance(raw, float) and pd.isna(raw)):
            raw = row.get("win_decimal")
        if raw is None or (isinstance(raw, float) and pd.isna(raw)):
            raw = row.get("live_odds_decimal")
        try:
            dec = float(raw)
        except (TypeError, ValueError):
            dec = float("nan")
        odds.append(dec)

    if all(np.isfinite(o) and o > 1.0 for o in odds):
        devig = devig_exchange_probabilities(odds)
        if devig is not None:
            return _normalize_probabilities(np.asarray(devig, dtype=np.float64))

    return np.ones(n, dtype=np.float64) / float(n)


def _place_market_implied_prob(row: Mapping[str, Any]) -> float | None:
    for key in ("offered_place_decimal", "place_decimal", "place_back_price"):
        raw = row.get(key)
        if raw is None:
            continue
        try:
            dec = float(raw)
        except (TypeError, ValueError):
            continue
        if dec > 1.0:
            return 1.0 / dec
    return None


def _resolve_place_liquidity_gbp(row: Mapping[str, Any]) -> float | None:
    for key in ("matchbook_place_liquidity", "place_back_liquidity", "back_liquidity"):
        raw = row.get(key)
        if raw is None:
            continue
        try:
            val = float(raw)
        except (TypeError, ValueError):
            continue
        if np.isfinite(val) and val >= 0.0:
            return val
    return None


def build_place_alpha_payload(
    *,
    runner_id: str,
    true_place_prob: float,
    market_implied: float,
    edge_bps: float,
) -> dict[str, Any]:
    return {
        "signal": "PLACE_ALPHA_TARGET",
        "runner_id": str(runner_id),
        "true_place_prob": round(float(true_place_prob), 6),
        "market_implied_place_prob": round(float(market_implied), 6),
        "edge_bps": round(float(edge_bps), 2),
        "immutable": True,
    }


def apply_place_alpha_and_liquidity(frame: pd.DataFrame) -> pd.DataFrame:
    """Cross-reference corrected place probabilities vs exchange place odds; mute thin pools."""
    if frame.empty:
        return frame
    out = frame.copy()
    min_edge = min_place_edge_bps()
    floor = liquidity_floor_gbp()
    alpha_targets: list[str | None] = []
    edge_bps_col: list[float | None] = []
    muted: list[int] = []
    chip_edges: list[float | None] = []
    chip_active: list[int] = []

    for rec in out.to_dict(orient="records"):
        true_p = rec.get("model_place_prob")
        try:
            true_pf = float(true_p)
        except (TypeError, ValueError):
            true_pf = float("nan")
        market_p = _place_market_implied_prob(rec)
        liquidity = _resolve_place_liquidity_gbp(rec)
        edge_bps: float | None = None
        payload: str | None = None
        is_muted = 0
        chip_edge: float | None = None
        chip_on = 0

        if np.isfinite(true_pf) and market_p is not None and market_p > 0.0:
            edge_bps = (true_pf - market_p) * 10_000.0
            if edge_bps >= float(min_edge):
                payload = json.dumps(
                    build_place_alpha_payload(
                        runner_id=str(rec.get("runner_id") or ""),
                        true_place_prob=true_pf,
                        market_implied=market_p,
                        edge_bps=edge_bps,
                    ),
                    separators=(",", ":"),
                    sort_keys=True,
                )
                chip_edge = edge_bps / 100.0
                chip_on = 1

        if liquidity is not None and liquidity < float(floor):
            is_muted = 1
            payload = None
            chip_on = 0
            if "value_flag" in out.columns and int(rec.get("value_flag") or 0) == 1:
                pass

        alpha_targets.append(payload)
        edge_bps_col.append(edge_bps)
        muted.append(is_muted)
        chip_edges.append(chip_edge)
        chip_active.append(chip_on)

    out["place_edge_bps"] = edge_bps_col
    out["place_alpha_target"] = alpha_targets
    out["place_execution_muted"] = muted
    out["place_value_edge_pct"] = chip_edges
    out["place_value_chip_active"] = chip_active

    if "value_flag" in out.columns:
        mute_mask = pd.Series(muted, index=out.index).astype(int).eq(1)
        out.loc[mute_mask, "value_flag"] = 0
        if "value_gate_reason" in out.columns:
            out.loc[mute_mask, "value_gate_reason"] = "place_liquidity_floor"
        elif mute_mask.any():
            out["value_gate_reason"] = None
            out.loc[mute_mask, "value_gate_reason"] = "place_liquidity_floor"

    return out
