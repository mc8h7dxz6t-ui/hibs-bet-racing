from __future__ import annotations

import re
from dataclasses import dataclass

from hibs_racing.tips.courses import find_course_in_text

_TIME_RE = re.compile(r"\b(\d{1,2})[:.](\d{2})\b")
_SCHEDULE_LINE_RE = re.compile(r"^(\d{1,2})[.:](\d{2})\s+(.+)$")
_ODDS_FRAC_RE = re.compile(r"\b(\d+(?:\.\d+)?)\s*/\s*(\d+)\b")
_ODDS_DEC_RE = re.compile(r"(?:@|at|odds?\s*)\s*(\d+(?:\.\d+)?)\b", re.I)
_NAP_LINE_RE = re.compile(
    r"\b(NAP|NB|Next\s+Best|Best\s+Bet|Selection|Tip|Win\s+Only|E/W|Each[\s-]?Way)\b",
    re.I,
)
_STABLE_RE = re.compile(
    r"\b(stable|yard|connections|informant|inside\s+word|word\s+from|"
    r"strong\s+word|keen|well\s+in|ready\s+to\s+go)\b",
    re.I,
)
_HORSE_AFTER_DASH_RE = re.compile(
    r"[-–—]\s*([A-Z][A-Za-z''\-]+(?:\s+[A-Z][A-Za-z''\-]+){0,4})"
)
_HORSE_BEFORE_ODDS_RE = re.compile(
    r"([A-Z][A-Za-z''\-]+(?:\s+[A-Z][A-Za-z''\-]+){0,4})\s+(?:@|at|\d+(?:\.\d+)?/\d+|\d+(?:\.\d+)?/1\b)"
)
_NAP_HORSE_RE = re.compile(
    r"(?:NAP|NB|Selection|Tip|Best\s+Bet)\s*:?\s*([A-Z][A-Za-z''\-]+(?:\s+[A-Z][A-Za-z''\-]+){0,4})",
    re.I,
)
_SKIP_LINE_RE = re.compile(
    r"^(?:\d+(?:\.\d+)?\s*pt\s+)?(?:win\s+)?(?:each\s+way\s+)?"
    r"(?:double|treble|trixie|patent|lucky\s+\d+|accumulator|accas?)\b",
    re.I,
)


@dataclass
class ParsedTip:
    horse_name: str | None
    course: str | None
    off_time: str | None
    card_date: str | None
    odds_quoted: str | None
    odds_decimal: float | None
    bet_type: str
    stable_intel: str
    confidence: str | None
    raw_excerpt: str
    review_text: str | None = None


def fractional_to_decimal(num: str, den: str) -> float:
    return 1.0 + float(num) / float(den)


def parse_odds(text: str) -> tuple[str | None, float | None]:
    m = _ODDS_FRAC_RE.search(text)
    if m:
        quoted = f"{m.group(1)}/{m.group(2)}"
        try:
            return quoted, fractional_to_decimal(m.group(1), m.group(2))
        except (ValueError, ZeroDivisionError):
            return quoted, None
    m = _ODDS_DEC_RE.search(text)
    if m:
        try:
            val = float(m.group(1))
            if val > 1.0:
                return str(val), val
        except ValueError:
            pass
    return None, None


def normalize_off_time(hour: str, minute: str) -> str:
    h = int(hour)
    if h < 8:
        h += 12
    return f"{h:02d}:{minute}"


def title_case_horse(name: str) -> str:
    """REALIGN / WASHINGTON HEIGHTS → Realign / Washington Heights."""
    parts = name.strip().split()
    out: list[str] = []
    for part in parts:
        if part.isupper() and len(part) > 1:
            out.append(part.title())
        else:
            out.append(part[:1].upper() + part[1:].lower() if part else part)
    return " ".join(out)


def _detect_bet_type(text: str) -> str:
    lower = text.lower()
    if re.search(r"\b\d+(?:\.\d+)?\s*pt\s+ew\b", lower) or " each way" in lower or " e/w" in lower:
        return "each_way"
    if re.search(r"\bnap\b", text, re.I):
        return "nap"
    if re.search(r"\bnb\b", text, re.I):
        return "nb"
    if re.search(r"\b\d+(?:\.\d+)?\s*pt\s+win\b", lower) or "win only" in lower:
        return "win"
    if "place" in lower and "places" not in lower:
        return "place"
    if re.search(r"\bwin\b", lower):
        return "win"
    return "unknown"


def _detect_confidence(text: str) -> str | None:
    if re.search(r"\bNAP\b", text):
        return "NAP"
    if re.search(r"\bNB\b", text):
        return "NB"
    m = re.search(r"\b(Next Best|Best Bet)\b", text, re.I)
    return m.group(1).upper() if m else None


def _detect_stable(text: str) -> str:
    return "yes" if _STABLE_RE.search(text) else "unknown"


def _extract_horse(text: str) -> str | None:
    for pattern in (_NAP_HORSE_RE, _HORSE_AFTER_DASH_RE, _HORSE_BEFORE_ODDS_RE):
        m = pattern.search(text)
        if m:
            name = m.group(1).strip()
            if len(name) >= 3 and name.lower() not in {"each way", "win only", "best bet"}:
                return name
    return None


def _extract_time(text: str) -> str | None:
    m = _TIME_RE.search(text)
    if not m:
        return None
    return normalize_off_time(m.group(1), m.group(2))


def _parse_schedule_line(line: str) -> ParsedTip | None:
    """
    Tipster schedule format:
      2.33 Carlisle WASHINGTON HEIGHTS 9/2 1pt win NAP
      3.45 Carlisle ARCHER ROYAL 20/1 0.75pt ew 5 places (...)
    """
    stripped = line.strip()
    if not stripped:
        return None
    if re.search(r"\bgood luck\b", stripped, re.I) and not _ODDS_FRAC_RE.search(stripped):
        return None

    m = _SCHEDULE_LINE_RE.match(stripped)
    if not m:
        return None

    hour, minute, rest = m.group(1), m.group(2), m.group(3)
    course = find_course_in_text(rest)
    if not course:
        return None

    pos = rest.lower().find(course.lower())
    if pos != 0:
        return None
    after_course = rest[len(course) :].strip()
    if not after_course:
        return None

    odds_m = _ODDS_FRAC_RE.search(after_course)
    if not odds_m:
        return None

    horse_raw = after_course[: odds_m.start()].strip()
    if not horse_raw or not re.match(r"^[A-Z0-9]", horse_raw):
        return None
    if horse_raw.lower() in {"win", "ew", "each way"}:
        return None

    odds_q, odds_d = parse_odds(odds_m.group(0))
    horse = title_case_horse(horse_raw)

    return ParsedTip(
        horse_name=horse,
        course=course,
        off_time=normalize_off_time(hour, minute),
        card_date=None,
        odds_quoted=odds_q,
        odds_decimal=odds_d,
        bet_type=_detect_bet_type(stripped),
        stable_intel=_detect_stable(stripped),
        confidence=_detect_confidence(stripped),
        raw_excerpt=stripped[:500],
    )


def _is_tip_line(line: str) -> bool:
    if _parse_schedule_line(line):
        return True
    if len(line.strip()) < 6:
        return False
    has_course = find_course_in_text(line) is not None
    has_time = _TIME_RE.search(line) is not None
    has_odds = _ODDS_FRAC_RE.search(line) or _ODDS_DEC_RE.search(line)
    has_label = _NAP_LINE_RE.search(line) is not None
    has_horse = _extract_horse(line) is not None
    return (has_course and (has_time or has_odds or has_horse)) or (
        has_label and (has_horse or has_course)
    )


def _attach_tip_reviews(lines: list[str], tips: list[ParsedTip]) -> None:
    """Link prose review paragraphs that follow schedule lines (MIDNIGHT LIR is…)."""
    if not tips:
        return
    lookup: dict[str, ParsedTip] = {}
    for tip in tips:
        if tip.horse_name:
            lookup[tip.horse_name.upper()] = tip

    for line in lines:
        stripped = line.strip()
        if len(stripped) < 80 or _parse_schedule_line(stripped) or _SKIP_LINE_RE.search(stripped):
            continue
        upper = stripped.upper()
        for key, tip in lookup.items():
            if upper.startswith(key + " ") or upper.startswith(key + " IS") or upper.startswith(key + " HAS"):
                tip.review_text = stripped
                if tip.stable_intel == "unknown" and not _STABLE_RE.search(stripped):
                    tip.stable_intel = "no"
                break


def parse_tips_from_text(
    body: str,
    *,
    default_card_date: str | None = None,
    context_lines: int = 1,
) -> list[ParsedTip]:
    """Extract structured tips from plain email body or pasted section."""
    lines = [ln.strip() for ln in body.replace("\r\n", "\n").split("\n") if ln.strip()]
    tips: list[ParsedTip] = []
    seen: set[tuple[str | None, str | None, str | None, str | None]] = set()

    for i, line in enumerate(lines):
        scheduled = _parse_schedule_line(line)
        if scheduled:
            tip = scheduled
        elif _is_tip_line(line):
            block_lines = lines[max(0, i - context_lines) : min(len(lines), i + context_lines + 1)]
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
            continue

        tip.card_date = tip.card_date or default_card_date
        key = (tip.horse_name, tip.course, tip.off_time, tip.card_date)
        if key in seen:
            continue
        if not tip.horse_name and not tip.course:
            continue
        seen.add(key)
        tips.append(tip)

    _attach_tip_reviews(lines, tips)
    return tips
