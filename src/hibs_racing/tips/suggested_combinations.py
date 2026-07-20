"""Engine-suggested racing system bets when no tipster email combos exist."""

from __future__ import annotations

from typing import Any

import pandas as pd

from hibs_racing.tips.group_combinations import _COMBO_SPECS

_ENGINE_COMBO_DEFS: tuple[tuple[str, str, int], ...] = (
    ("double", "Engine double · top 2", 2),
    ("trixie", "Engine Trixie · top 3", 3),
    ("lucky_15", "Engine Lucky 15 · top 4", 4),
)


def _pick_to_leg(pick: dict[str, Any]) -> dict[str, Any]:
    event_parts = [p for p in (pick.get("course"), pick.get("off_time")) if p]
    odds = pick.get("win_decimal")
    if odds is None:
        odds = pick.get("offered_place_decimal")
    try:
        odds_decimal = float(odds) if odds is not None else None
    except (TypeError, ValueError):
        odds_decimal = None
    return {
        "event": " ".join(event_parts) if event_parts else "—",
        "selection": pick.get("horse_name") or "—",
        "market": "each_way",
        "odds_decimal": odds_decimal,
        "runner_id": pick.get("runner_id"),
    }


def build_engine_combinations(
    frame: pd.DataFrame | None = None,
    *,
    top_n: int = 6,
) -> dict[str, Any]:
    """
    Build double / Trixie / Lucky 15 from monitor top picks (one per race).

    Returns empty combinations when fewer than two qualifying picks exist.
    """
    from hibs_racing.monitor import top_places_of_day

    picks = top_places_of_day(frame, top_n=top_n)
    if len(picks) < 2:
        return {"combinations": [], "singles": [], "pick_count": len(picks)}

    legs = [_pick_to_leg(p) for p in picks]
    combinations: list[dict[str, Any]] = []

    for combo_type, label, leg_count in _ENGINE_COMBO_DEFS:
        if len(legs) < leg_count:
            continue
        sel, bet_count = _COMBO_SPECS[combo_type]
        combinations.append(
            {
                "type": combo_type,
                "label": label,
                "stake_units": None,
                "bet_count": bet_count,
                "legs": legs[:leg_count],
                "source": "engine",
            }
        )

    used_in_lucky = min(4, len(legs))
    singles = legs[used_in_lucky:] if len(legs) > used_in_lucky else []

    return {
        "combinations": combinations,
        "singles": singles,
        "pick_count": len(picks),
    }
