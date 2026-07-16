from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from hibs_racing.tips.parse_body import ParsedTip, parse_tips_from_text, _parse_schedule_line, _is_tip_line
from hibs_racing.tips.parse_body import (
    _extract_horse,
    _extract_time,
    parse_odds,
    _detect_bet_type,
    _detect_stable,
    _detect_confidence,
)
from hibs_racing.tips.courses import find_course_in_text

_COMBO_HEADER_RE = re.compile(
    r"^(?:(\d+(?:\.\d+)?)\s*pt\s+)?(?:win\s+)?(each\s+way\s+)?"
    r"(double|treble|trixie|patent|lucky\s+(\d+)|accumulator|accas?)\b",
    re.I,
)

_COMBO_SPECS: dict[str, tuple[int, int]] = {
    "double": (2, 1),
    "ew_double": (2, 1),
    "treble": (3, 1),
    "trixie": (3, 4),
    "patent": (3, 7),
    "lucky_15": (4, 15),
    "lucky_31": (5, 31),
    "lucky_63": (6, 63),
    "accumulator": (0, 0),
    "acca": (0, 0),
}


@dataclass
class CombinationHeader:
    type: str
    label: str
    stake_units: float | None
    bet_count: int
    selection_count: int
    market: str


def parse_combination_header(line: str) -> CombinationHeader | None:
    stripped = line.strip()
    m = _COMBO_HEADER_RE.search(stripped)
    if not m:
        return None

    stake_raw, ew_prefix, kind_raw, lucky_num = m.group(1), m.group(2), m.group(3), m.group(4)
    kind = kind_raw.lower().replace(" ", "_")
    if kind.startswith("acca"):
        kind = "acca"
    elif kind.startswith("accumulator"):
        kind = "accumulator"

    combo_type = kind
    market = "each_way" if ew_prefix else "win"
    if ew_prefix and kind == "double":
        combo_type = "ew_double"

    if kind == "lucky" and lucky_num:
        combo_type = f"lucky_{lucky_num}"
        sel, bets = _lucky_spec(int(lucky_num))
    else:
        spec = _COMBO_SPECS.get(combo_type)
        if not spec:
            return None
        sel, bets = spec

    stake_units = float(stake_raw) if stake_raw else None
    return CombinationHeader(
        type=combo_type,
        label=stripped,
        stake_units=stake_units,
        bet_count=bets,
        selection_count=sel,
        market=market,
    )


def _lucky_spec(lucky_number: int) -> tuple[int, int]:
    """Map Lucky N name to (selection_count, bet_count)."""
    known = {15: (4, 15), 31: (5, 31), 63: (6, 63)}
    if lucky_number in known:
        return known[lucky_number]
    for selections in range(2, 12):
        bet_count = (2**selections) - 1
        if bet_count == lucky_number:
            return selections, bet_count
    return max(2, lucky_number // 4), lucky_number


def _parse_line_as_tip(
    line: str,
    lines: list[str],
    index: int,
    default_card_date: str | None,
    context_lines: int = 1,
) -> ParsedTip | None:
    scheduled = _parse_schedule_line(line)
    if scheduled:
        tip = scheduled
    elif _is_tip_line(line):
        block_lines = lines[max(0, index - context_lines) : min(len(lines), index + context_lines + 1)]
        block = "\n".join(block_lines)
        course = find_course_in_text(block) or find_course_in_text(line)
        off_time = _extract_time(line) or _extract_time(block)
        horse = _extract_horse(line) or _extract_horse(block)
        odds_q, odds_d = parse_odds(line) or (None, None)
        if not odds_q:
            odds_q, odds_d = parse_odds(block)
        tip = ParsedTip(
            horse_name=horse,
            course=course,
            off_time=off_time,
            card_date=default_card_date,
            odds_quoted=odds_q,
            odds_decimal=odds_d,
            bet_type=_detect_bet_type(block),
            stable_intel=_detect_stable(block),
            confidence=_detect_confidence(block),
            raw_excerpt=line[:500],
        )
    else:
        return None

    tip.card_date = tip.card_date or default_card_date
    if not tip.horse_name and not tip.course:
        return None
    return tip


def parsed_tip_to_leg(tip: ParsedTip, runner_id: str | None = None) -> dict[str, Any]:
    event_parts: list[str] = []
    if tip.course:
        event_parts.append(tip.course)
    if tip.off_time:
        event_parts.append(tip.off_time)
    market = tip.bet_type if tip.bet_type in {"win", "each_way", "place", "nap", "nb"} else "win"
    return {
        "event": " ".join(event_parts) if event_parts else "—",
        "selection": tip.horse_name or "—",
        "market": market,
        "odds_decimal": tip.odds_decimal,
        "runner_id": runner_id,
    }


def _tip_key(tip: ParsedTip) -> tuple[str | None, str | None, str | None, str | None]:
    return (tip.horse_name, tip.course, tip.off_time, tip.card_date)


def _build_leg(tip: ParsedTip, lookup: dict[tuple, str | None]) -> dict[str, Any]:
    rid = lookup.get(_tip_key(tip))
    return parsed_tip_to_leg(tip, runner_id=rid)


def group_tips_from_text(
    body: str,
    *,
    default_card_date: str | None = None,
    runner_lookup: dict[tuple, str | None] | None = None,
) -> dict[str, Any]:
    """Return combinations + singles from email body text."""
    lines = [ln.strip() for ln in body.replace("\r\n", "\n").split("\n") if ln.strip()]
    lookup = runner_lookup or {}

    tips_ordered: list[tuple[int, ParsedTip]] = []
    headers_ordered: list[tuple[int, CombinationHeader]] = []
    seen: set[tuple] = set()

    for i, line in enumerate(lines):
        header = parse_combination_header(line)
        if header:
            headers_ordered.append((i, header))
            continue
        tip = _parse_line_as_tip(line, lines, i, default_card_date)
        if not tip:
            continue
        key = _tip_key(tip)
        if key in seen:
            continue
        seen.add(key)
        tips_ordered.append((i, tip))

    assigned: set[int] = set()
    combinations: list[dict[str, Any]] = []

    for hi, (line_idx, header) in enumerate(headers_ordered):
        next_header_line = headers_ordered[hi + 1][0] if hi + 1 < len(headers_ordered) else len(lines) + 1
        prev_header_line = headers_ordered[hi - 1][0] if hi > 0 else -1

        following = [
            (li, t)
            for li, t in tips_ordered
            if li not in assigned and line_idx < li < next_header_line
        ]
        preceding = [
            (li, t)
            for li, t in tips_ordered
            if li not in assigned and prev_header_line < li < line_idx
        ]

        use_prospective = bool(following) and (
            not preceding or (following[0][0] - line_idx) <= (line_idx - preceding[-1][0])
        )

        if header.type in {"accumulator", "acca"}:
            legs_pool = following if use_prospective else preceding[-max(len(preceding), 0) :]
        elif use_prospective:
            legs_pool = following[: header.selection_count] if header.selection_count else following
        else:
            legs_pool = preceding[-header.selection_count :] if header.selection_count else preceding

        for li, _ in legs_pool:
            assigned.add(li)

        combo_legs = [_build_leg(t, lookup) for _, t in legs_pool]
        if header.market and header.market != "win":
            for leg in combo_legs:
                if leg.get("market") == "win":
                    leg["market"] = header.market

        combinations.append(
            {
                "type": header.type,
                "label": header.label,
                "stake_units": header.stake_units,
                "bet_count": header.bet_count,
                "legs": combo_legs,
            }
        )

    singles = [_build_leg(t, lookup) for li, t in tips_ordered if li not in assigned]

    return {"combinations": combinations, "singles": singles}


def parse_tips_grouped_from_text(
    body: str,
    *,
    default_card_date: str | None = None,
    runner_lookup: dict[tuple, str | None] | None = None,
) -> dict[str, Any]:
    """Grouped parse; flat tips remain available via parse_tips_from_text."""
    result = group_tips_from_text(
        body,
        default_card_date=default_card_date,
        runner_lookup=runner_lookup,
    )
    result["tips_flat"] = parse_tips_from_text(body, default_card_date=default_card_date)
    return result
