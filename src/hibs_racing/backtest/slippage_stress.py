"""Odds slippage stress — recompute EV / raw value flags at worse offered prices."""

from __future__ import annotations

import pandas as pd

from hibs_racing.config import load_config
from hibs_racing.place.ew_ev import EachWayQuote, each_way_ev


def worse_win_decimal(win_decimal: float, slip_bps: float) -> float:
    """
    Bettor receives worse odds: decimal decreases (longer implied probability).
    ``slip_bps`` = basis points off the offered price (50 → 0.50%).
    """
    if slip_bps <= 0:
        return float(win_decimal)
    factor = 1.0 - (float(slip_bps) / 10_000.0)
    return max(1.01, float(win_decimal) * factor)


def apply_slippage_to_frame(frame: pd.DataFrame, slip_bps: float, *, paper_cfg: dict | None = None) -> pd.DataFrame:
    """
    Return a copy with stressed ``win_decimal``, ``place_ev``, ``ew_combined_ev``, and ``flag_raw``.
    Model probabilities are unchanged; only the quote moves.
    """
    if frame.empty or slip_bps <= 0:
        return frame.copy()
    cfg = paper_cfg or load_config().get("paper", {})
    min_place_ev = float(cfg.get("min_place_ev", 0.05))
    min_combo = float(cfg.get("min_combo_bayes_place", 0.22))
    default_frac = float(cfg.get("default_place_fraction", 0.25))
    default_places = int(cfg.get("default_places", 3))

    out = frame.copy()
    place_evs: list[float | None] = []
    combined: list[float | None] = []
    flags: list[int] = []

    for rec in out.to_dict(orient="records"):
        win = rec.get("win_decimal")
        if win is None or (isinstance(win, float) and pd.isna(win)):
            place_evs.append(rec.get("place_ev"))
            combined.append(rec.get("ew_combined_ev"))
            flags.append(0)
            continue
        stressed = worse_win_decimal(float(win), slip_bps)
        quote = EachWayQuote(
            win_decimal=stressed,
            place_fraction=float(rec.get("place_fraction") or default_frac),
            places=int(rec.get("places") or default_places),
        )
        ev = each_way_ev(
            float(rec["model_win_prob"]),
            float(rec["model_place_prob"]),
            quote,
        )
        place_evs.append(ev.place_ev)
        combined.append(ev.combined_ev)
        combo = float(rec.get("combo_bayes_place") or 0)
        flags.append(1 if ev.place_ev >= min_place_ev and combo >= min_combo else 0)

    out["win_decimal"] = out["win_decimal"].apply(
        lambda w: worse_win_decimal(float(w), slip_bps) if w is not None and not pd.isna(w) else w
    )
    out["place_ev"] = place_evs
    out["ew_combined_ev"] = combined
    out["flag_raw"] = flags
    return out


def default_slip_bps_list(paper_cfg: dict | None = None) -> list[float]:
    cfg = paper_cfg or load_config().get("paper", {})
    raw = cfg.get("slippage_stress_bps")
    if isinstance(raw, list) and raw:
        return [float(x) for x in raw]
    return [0.0, 25.0, 50.0]
