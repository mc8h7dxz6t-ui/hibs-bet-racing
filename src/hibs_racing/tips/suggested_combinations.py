"""Engine-suggested racing system bets when no tipster email combos exist."""

from __future__ import annotations

from typing import Any

import pandas as pd

from hibs_racing.tips.group_combinations import _COMBO_SPECS

_ENGINE_COMBO_DEFS: tuple[tuple[str, str, int], ...] = (
    ("double", "Value lane double · top 2 EV", 2),
    ("trixie", "Value lane Trixie · top 3 EV", 3),
    ("lucky_15", "Value lane Lucky 15 · top 4 EV", 4),
)


def _fmt_ev(value: object) -> float | None:
    try:
        if value is None:
            return None
        return round(float(value), 3)
    except (TypeError, ValueError):
        return None


def _pick_to_leg(pick: dict[str, Any]) -> dict[str, Any]:
    event_parts = [p for p in (pick.get("course"), pick.get("off_time")) if p]
    odds = pick.get("win_decimal")
    if odds is None:
        odds = pick.get("offered_place_decimal")
    try:
        odds_decimal = float(odds) if odds is not None else None
    except (TypeError, ValueError):
        odds_decimal = None
    ev = _fmt_ev(pick.get("ew_combined_ev"))
    return {
        "event": " ".join(event_parts) if event_parts else "—",
        "selection": pick.get("horse_name") or "—",
        "market": "each_way",
        "odds_decimal": odds_decimal,
        "runner_id": pick.get("runner_id"),
        "value_lane_rank": pick.get("value_lane_rank") or pick.get("day_rank"),
        "ew_combined_ev": ev,
        "value_flag": bool(pick.get("value_flag")),
    }


def build_engine_combinations(
    frame: pd.DataFrame | None = None,
    *,
    top_n: int = 6,
) -> dict[str, Any]:
    """
    Build double / Trixie / Lucky 15 from value-lane picks (EV-ranked, one per race).

    Value lane is where paper ROI signal concentrates — only value_flag runners with
    positive each-way EV are eligible. Returns empty when fewer than two qualify.
    """
    from hibs_racing.monitor import top_value_lane_picks

    picks = top_value_lane_picks(frame, top_n=top_n)
    if len(picks) < 2:
        return {
            "combinations": [],
            "singles": [],
            "pick_count": len(picks),
            "pick_source": "value_lane",
            "message": (
                "Need at least two value-lane runners (value_flag + positive EV) for system bets. "
                "Refresh cards and Matchbook odds, then check the Value lane panel."
            ),
        }

    legs = [_pick_to_leg(p) for p in picks]
    combinations: list[dict[str, Any]] = []

    for combo_type, label, leg_count in _ENGINE_COMBO_DEFS:
        if len(legs) < leg_count:
            continue
        sel, bet_count = _COMBO_SPECS[combo_type]
        combo_legs = legs[:leg_count]
        combinations.append(
            {
                "type": combo_type,
                "label": label,
                "stake_units": None,
                "bet_count": bet_count,
                "legs": combo_legs,
                "source": "engine",
                "pick_source": "value_lane",
                "combined_ev_hint": _fmt_ev(
                    sum(float(leg.get("ew_combined_ev") or 0) for leg in combo_legs)
                ),
            }
        )

    used_in_lucky = min(4, len(legs))
    singles = legs[used_in_lucky:] if len(legs) > used_in_lucky else []

    return {
        "combinations": combinations,
        "singles": singles,
        "pick_count": len(picks),
        "pick_source": "value_lane",
        "message": None,
    }
