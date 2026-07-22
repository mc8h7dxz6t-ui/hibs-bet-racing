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


def _pick_to_leg(pick: dict[str, Any], *, day_label: str | None = None) -> dict[str, Any]:
    card_date = str(pick.get("card_date") or "")[:10] or None
    label = day_label or pick.get("day_label")
    course_time = [p for p in (pick.get("course"), pick.get("off_time")) if p]
    event_parts: list[str] = []
    if label:
        event_parts.append(str(label))
    if course_time:
        event_parts.append(" ".join(course_time))
    odds = pick.get("win_decimal")
    if odds is None:
        odds = pick.get("offered_place_decimal")
    try:
        odds_decimal = float(odds) if odds is not None else None
    except (TypeError, ValueError):
        odds_decimal = None
    ev = _fmt_ev(pick.get("ew_combined_ev"))
    return {
        "event": " · ".join(event_parts) if event_parts else "—",
        "selection": pick.get("horse_name") or "—",
        "market": "each_way",
        "odds_decimal": odds_decimal,
        "runner_id": pick.get("runner_id"),
        "card_date": card_date,
        "day_label": label,
        "course": pick.get("course"),
        "off_time": pick.get("off_time"),
        "value_lane_rank": pick.get("value_lane_rank") or pick.get("day_rank"),
        "ew_combined_ev": ev,
        "value_flag": bool(pick.get("value_flag")),
    }


def _build_combinations_from_picks(
    picks: list[dict[str, Any]],
    *,
    card_date: str | None = None,
    day_label: str | None = None,
) -> dict[str, Any]:
    if len(picks) < 2:
        return {
            "combinations": [],
            "singles": [_pick_to_leg(p, day_label=day_label) for p in picks],
            "pick_count": len(picks),
            "card_date": card_date,
            "day_label": day_label,
            "message": (
                "Need at least two value-lane runners (value_flag + positive EV) for system bets. "
                "Refresh cards and Matchbook odds, then check the Value lane panel."
                if len(picks) < 2
                else None
            ),
        }

    legs = [_pick_to_leg(p, day_label=day_label) for p in picks]
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
                "card_date": card_date,
                "day_label": day_label,
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
        "card_date": card_date,
        "day_label": day_label,
        "message": None,
    }


def build_engine_combinations_by_day(
    frame: pd.DataFrame | None = None,
    *,
    top_n: int = 6,
    prefer_card_date: str | None = None,
) -> dict[str, Any]:
    """
    Build double / Trixie / Lucky 15 per card_date — today and tomorrow kept separate.

    Value lane picks never cross midnight: each day's combos only use runners from that card.
    """
    from hibs_racing.cards.query import load_scored_cards
    from hibs_racing.cards.window import primary_card_date
    from hibs_racing.monitor import top_value_lane_picks
    from hibs_racing.web_service import day_label

    if frame is None:
        frame = load_scored_cards()
    if frame.empty or "card_date" not in frame.columns:
        return {
            "days": [],
            "combinations": [],
            "singles": [],
            "pick_count": 0,
            "pick_source": "value_lane",
            "card_date": prefer_card_date,
            "day_label": None,
            "message": (
                "Need at least two value-lane runners (value_flag + positive EV) for system bets. "
                "Refresh cards and Matchbook odds, then check the Value lane panel."
            ),
        }

    dates = sorted(frame["card_date"].astype(str).str[:10].unique())
    days: list[dict[str, Any]] = []
    for card_date in dates:
        day_frame = frame[frame["card_date"].astype(str).str[:10] == card_date]
        picks = top_value_lane_picks(day_frame, top_n=top_n)
        label = day_label(card_date)
        day_payload = _build_combinations_from_picks(
            picks,
            card_date=card_date,
            day_label=label,
        )
        if picks or day_payload["combinations"] or day_payload["singles"]:
            days.append(day_payload)

    primary_date = prefer_card_date or primary_card_date(frame) or (dates[-1] if dates else None)
    primary_day = next((d for d in days if d.get("card_date") == primary_date), None)
    if primary_day is None and days:
        primary_day = days[0]
        primary_date = primary_day.get("card_date")

    total_picks = sum(int(d.get("pick_count") or 0) for d in days)
    message = None
    combo_count = sum(len(d.get("combinations") or []) for d in days)
    if combo_count == 0:
        message = (
            "Need at least two value-lane runners per day (value_flag + positive EV) for system bets. "
            "Refresh cards and Matchbook odds, then check the Value lane panel."
        )

    return {
        "days": days,
        "combinations": (primary_day or {}).get("combinations") or [],
        "singles": (primary_day or {}).get("singles") or [],
        "pick_count": int((primary_day or {}).get("pick_count") or total_picks),
        "pick_source": "value_lane",
        "card_date": primary_date,
        "day_label": (primary_day or {}).get("day_label"),
        "message": message,
    }


def build_engine_combinations(
    frame: pd.DataFrame | None = None,
    *,
    top_n: int = 6,
    card_date: str | None = None,
) -> dict[str, Any]:
    """
    Build double / Trixie / Lucky 15 from value-lane picks (EV-ranked, one per race).

    When the frame spans multiple card dates, combinations are built per day and the
    primary day (upcoming card) is also exposed at the top level for backward compatibility.
    """
    payload = build_engine_combinations_by_day(
        frame,
        top_n=top_n,
        prefer_card_date=card_date,
    )
    payload.pop("days", None)
    return payload
