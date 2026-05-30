from __future__ import annotations

import re
from dataclasses import asdict, dataclass, fields

from hibs_racing.nlp.normalize import normalize_comment

# Each tag maps to weighted phrase patterns. Severity accumulates on multiple hits.
TAG_PATTERNS: dict[str, list[tuple[str, float]]] = {
    "late_pace_acceleration": [
        (r"smooth headway", 1.0),
        (r"headway \d furlong", 0.9),
        (r"\d furlongs out.*?headway", 0.9),
        (r"headway inside", 0.9),
        (r"picked up(?: well)?", 0.85),
        (r"stayed on strongly", 1.0),
        (r"stayed on well", 0.8),
        (r"ran on well", 0.75),
        (r"kept on well", 0.7),
        (r"made (?:good )?headway", 0.85),
        (r"headway(?: inside)? final furlong", 0.95),
    ],
    "finishing_burst": [
        (r"quickened to lead", 1.0),
        (r"quickened", 0.95),
        (r"finished fast", 0.9),
        (r"ran on (?:well|strongly)", 0.75),
        (r"fast finish", 0.95),
        (r"strong finish", 0.9),
        (r"finished (?:strongly|well)", 0.8),
        (r"quickening", 0.95),
        (r"ran on strongly", 0.85),
    ],
    "stamina_deficit": [
        (r"faded(?: inside)? final furlong", 1.0),
        (r"faded", 0.95),
        (r"tired(?: inside)? final furlong", 1.0),
        (r"tired", 0.9),
        (r"no extra", 1.0),
        (r"weakened(?: inside)? final furlong", 1.0),
        (r"weakened", 0.9),
        (r"empty(?: inside)?", 0.85),
        (r"outpaced", 0.7),
        (r"could not quicken", 0.9),
        (r"one paced", 0.75),
    ],
    "trouble_in_running": [
        (r"hampered", 1.0),
        (r"short of room", 1.0),
        (r"bumped", 0.9),
        (r"checked", 0.85),
        (r"denied (?:a )?clear run", 0.95),
        (r"unsuited by(?: the)? pace", 0.7),
        (r"carried (?:right )?wide", 0.75),
    ],
    "prominent_early": [
        (r"\bled\b", 1.0),
        (r"pressed leader", 0.95),
        (r"disputed lead", 0.95),
        (r"made (?:all|most of)", 0.85),
        (r"prominent", 0.8),
        (r"with leader", 0.75),
    ],
    "held_up": [
        (r"held up", 1.0),
        (r"in rear", 0.85),
        (r"towards rear", 0.8),
        (r"rear of mid-?division", 0.75),
        (r"waited with", 0.7),
    ],
}

COMPILED: dict[str, list[tuple[re.Pattern[str], float]]] = {
    tag: [(re.compile(pat), weight) for pat, weight in patterns]
    for tag, patterns in TAG_PATTERNS.items()
}


@dataclass
class CommentTags:
    late_pace_acceleration: float = 0.0
    finishing_burst: float = 0.0
    stamina_deficit: float = 0.0
    trouble_in_running: float = 0.0
    prominent_early: float = 0.0
    held_up: float = 0.0

    @property
    def tag_count(self) -> int:
        return sum(1 for f in fields(self) if getattr(self, f.name) > 0)

    def as_dict(self) -> dict[str, float | int]:
        payload = {f.name: getattr(self, f.name) for f in fields(self)}
        payload["tag_count"] = self.tag_count
        return payload


def tag_comment(text: str | None, *, race_type: str | None = None) -> CommentTags:
    """Extract pace/ trip tags from a running comment. race_type reserved for flat/jumps splits."""
    _ = race_type  # flat vs jumps lexicon tweaks come in v2
    norm = normalize_comment(text).normalized
    if not norm:
        return CommentTags()

    scores: dict[str, float] = {tag: 0.0 for tag in TAG_PATTERNS}
    for tag, patterns in COMPILED.items():
        for pattern, weight in patterns:
            if pattern.search(norm):
                scores[tag] = min(1.0, scores[tag] + weight)

    return CommentTags(**scores)
