from __future__ import annotations

import re
from dataclasses import dataclass

# UK/Ireland racing shorthand → expanded tokens for regex matching.
ABBREV_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    (r"\b2f\b", "2 furlongs"),
    (r"\b1f\b", "1 furlong"),
    (r"\b3f\b", "3 furlongs"),
    (r"\b4f\b", "4 furlongs"),
    (r"\b5f\b", "5 furlongs"),
    (r"\b6f\b", "6 furlongs"),
    (r"\b7f\b", "7 furlongs"),
    (r"\bhd\b", "head"),
    (r"\bnk\b", "neck"),
    (r"\bshd\b", "short head"),
    (r"\bnse\b", "nose"),
    (r"\bstr\b", "stretched"),
    (r"\bpu\b", "pulled up"),
    (r"\bur\b", "unseated rider"),
    (r"\bf\b", "furlong"),
)

WHITESPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class NormalizedComment:
    raw: str
    normalized: str


def normalize_comment(text: str | None) -> NormalizedComment:
    raw = (text or "").strip()
    if not raw:
        return NormalizedComment(raw="", normalized="")

    lowered = raw.lower()
    for pattern, replacement in ABBREV_REPLACEMENTS:
        lowered = re.sub(pattern, replacement, lowered)
    normalized = WHITESPACE_RE.sub(" ", lowered).strip()
    return NormalizedComment(raw=raw, normalized=normalized)
