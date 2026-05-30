from __future__ import annotations

import re
from dataclasses import dataclass, fields

from hibs_racing.nlp.normalize import normalize_comment
from hibs_racing.nlp.tagger_regex import TAG_PATTERNS, CommentTags, tag_comment

# Sectional timing markers — proxy for GPS furlong splits.
HEADWAY_AT_F_RE = re.compile(
    r"(?:headway|picked up|smooth headway|made headway).*?(\d+) furlong"
)
HEADWAY_AT_F_ALT_RE = re.compile(r"(\d+) furlong(?:s)? out.*?headway")
FINAL_FURLONG_RE = re.compile(r"(?:inside )?final furlong")
QUICKENED_TO_LEAD_RE = re.compile(r"quickened to lead")
FADE_FINAL_RE = re.compile(
    r"(?:faded|weakened|no extra|tired|empty).*?(?:inside )?final furlong"
    r"|(?:inside )?final furlong.*?(?:faded|weakened|no extra|tired|empty)"
)
LATE_ACTION_FINAL_RE = re.compile(
    r"(?:quickened|stayed on|ran on|finished|headway).*?(?:inside )?final furlong"
)

PACE_LEVEL = ("none", "low", "medium", "high")
BURST_LEVEL = ("none", "good", "high", "elite")


@dataclass
class SectionalProxyFeatures:
    """
    GPS sectional proxy from running comments — discrete tags for ML rankers.

    Maps qualitative clerk text to structured pace features, e.g.:
      "smooth headway 2f out"  -> LatePaceAcceleration=high, headway_at_furlongs=2
      "quickened to lead"      -> FinishingBurst=elite
      "faded inside final furlong" -> StaminaDeficit=True
    """

    late_pace_acceleration: float = 0.0
    finishing_burst: float = 0.0
    stamina_deficit: float = 0.0
    trouble_in_running: float = 0.0
    prominent_early: float = 0.0
    held_up: float = 0.0

    late_pace_level: int = 0
    finishing_burst_level: int = 0
    stamina_deficit_flag: bool = False

    headway_at_furlongs: float | None = None
    fade_in_final_furlong: bool = False
    quickened_to_lead: bool = False
    late_action_in_final_furlong: bool = False
    sectional_composite: float = 0.0
    parser_backend: str = "regex"

    @property
    def tag_count(self) -> int:
        return sum(
            1
            for name in (
                "late_pace_acceleration",
                "finishing_burst",
                "stamina_deficit",
                "trouble_in_running",
                "prominent_early",
                "held_up",
            )
            if getattr(self, name) > 0
        )

    @property
    def LatePaceAcceleration(self) -> str:
        return PACE_LEVEL[self.late_pace_level]

    @property
    def FinishingBurst(self) -> str:
        return BURST_LEVEL[self.finishing_burst_level]

    @property
    def StaminaDeficit(self) -> bool:
        return self.stamina_deficit_flag

    def elite_labels(self) -> dict[str, str | bool | float | None]:
        return {
            "LatePaceAcceleration": self.LatePaceAcceleration,
            "FinishingBurst": self.FinishingBurst,
            "StaminaDeficit": self.StaminaDeficit,
            "headway_at_furlongs": self.headway_at_furlongs,
            "sectional_composite": round(self.sectional_composite, 3),
        }

    def as_dict(self) -> dict:
        base = {f.name: getattr(self, f.name) for f in fields(self)}
        base["tag_count"] = self.tag_count
        base["elite_labels"] = self.elite_labels()
        return base


def _pace_level(score: float, *, headway_at_f: float | None) -> int:
    adjusted = score
    if headway_at_f is not None and headway_at_f <= 2.5:
        adjusted = min(1.0, score + 0.15)
    if adjusted >= 0.85:
        return 3
    if adjusted >= 0.55:
        return 2
    if adjusted >= 0.25:
        return 1
    return 0


def _burst_level(score: float, *, quickened_to_lead: bool, late_final: bool) -> int:
    if quickened_to_lead:
        return 3
    adjusted = score
    if late_final:
        adjusted = min(1.0, score + 0.1)
    if adjusted >= 0.95:
        return 3
    if adjusted >= 0.7:
        return 2
    if adjusted >= 0.35:
        return 1
    return 0


def _extract_timing(norm: str) -> dict:
    headway_f = None
    for pattern in (HEADWAY_AT_F_RE, HEADWAY_AT_F_ALT_RE):
        match = pattern.search(norm)
        if match:
            headway_f = float(match.group(1))
            break

    return {
        "headway_at_furlongs": headway_f,
        "fade_in_final_furlong": bool(FADE_FINAL_RE.search(norm)),
        "quickened_to_lead": bool(QUICKENED_TO_LEAD_RE.search(norm)),
        "late_action_in_final_furlong": bool(LATE_ACTION_FINAL_RE.search(norm)),
        "mentions_final_furlong": bool(FINAL_FURLONG_RE.search(norm)),
    }


def _composite(
    tags: CommentTags,
    *,
    timing: dict,
    late_pace_level: int,
    burst_level: int,
    stamina_flag: bool,
) -> float:
    boost = tags.late_pace_acceleration * 0.35 + tags.finishing_burst * 0.35
    boost += late_pace_level * 0.05 + burst_level * 0.05
    if timing["quickened_to_lead"]:
        boost += 0.15
    if timing["headway_at_furlongs"] is not None and timing["headway_at_furlongs"] <= 2.5:
        boost += 0.1
    if timing["late_action_in_final_furlong"]:
        boost += 0.08

    penalty = tags.stamina_deficit * 0.45
    if stamina_flag and timing["fade_in_final_furlong"]:
        penalty += 0.25
    if tags.trouble_in_running > 0:
        penalty -= 0.05  # trouble can excuse a weak finish — slight uplift

    return max(0.0, min(1.0, boost - penalty))


def extract_sectional_features(
    text: str | None,
    *,
    race_type: str | None = None,
    base_tags: CommentTags | None = None,
    parser_backend: str = "regex",
) -> SectionalProxyFeatures:
    """Reverse-engineer sectional pace proxies from a running comment."""
    norm = normalize_comment(text).normalized
    if not norm:
        return SectionalProxyFeatures(parser_backend=parser_backend)

    tags = base_tags or tag_comment(norm, race_type=race_type)
    timing = _extract_timing(norm)

    stamina_flag = tags.stamina_deficit >= 0.25 or timing["fade_in_final_furlong"]
    late_pace_level = _pace_level(
        tags.late_pace_acceleration, headway_at_f=timing["headway_at_furlongs"]
    )
    burst_level = _burst_level(
        tags.finishing_burst,
        quickened_to_lead=timing["quickened_to_lead"],
        late_final=timing["late_action_in_final_furlong"],
    )

    composite = _composite(
        tags,
        timing=timing,
        late_pace_level=late_pace_level,
        burst_level=burst_level,
        stamina_flag=stamina_flag,
    )

    return SectionalProxyFeatures(
        late_pace_acceleration=tags.late_pace_acceleration,
        finishing_burst=tags.finishing_burst,
        stamina_deficit=tags.stamina_deficit,
        trouble_in_running=tags.trouble_in_running,
        prominent_early=tags.prominent_early,
        held_up=tags.held_up,
        late_pace_level=late_pace_level,
        finishing_burst_level=burst_level,
        stamina_deficit_flag=stamina_flag,
        headway_at_furlongs=timing["headway_at_furlongs"],
        fade_in_final_furlong=timing["fade_in_final_furlong"],
        quickened_to_lead=timing["quickened_to_lead"],
        late_action_in_final_furlong=timing["late_action_in_final_furlong"],
        sectional_composite=composite,
        parser_backend=parser_backend,
    )


def merge_tag_scores(base: CommentTags, boost: dict[str, float]) -> CommentTags:
    """Merge spaCy/regex boosts — take max per tag, cap at 1.0."""
    merged = {}
    for tag in TAG_PATTERNS:
        merged[tag] = min(1.0, max(getattr(base, tag), boost.get(tag, 0.0)))
    return CommentTags(**merged)
