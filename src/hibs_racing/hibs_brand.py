"""Hibs Racing Intelligence — brand assets and template context."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

HIBS_BADGE_PRIMARY = "logo_hibs_racing.svg"
HIBS_BADGE_HARP = "badge_harp_embroidered.png"
HIBS_RACING_LOGO = "badge_hibs_racing_oval.png"
HIBS_HERO_HORSE = "hero_horse.png"
HIBS_HORSE_CLUB_REF = "logo_horse_club_ref.png"

HIBS_HERITAGE_BADGES: list[dict[str, Any]] = [
    {"file": HIBS_BADGE_HARP, "label": "Golden harp shield", "era": "heritage"},
]

HIBS_WATERMARK_BADGES: list[str] = [HIBS_BADGE_HARP]


def hibs_brand_context() -> dict[str, Any]:
    ranker_path = Path(__file__).resolve().parents[2] / "data" / "models" / "lgbm_ranker.txt"
    return {
        "hibs_badge_primary": HIBS_BADGE_PRIMARY,
        "hibs_badge_harp": HIBS_BADGE_HARP,
        "hibs_racing_logo": HIBS_RACING_LOGO,
        "hibs_hero_horse": HIBS_HERO_HORSE,
        "hibs_horse_club_ref": HIBS_HORSE_CLUB_REF,
        "hibs_heritage_badges": HIBS_HERITAGE_BADGES,
        "hibs_watermark_badges": HIBS_WATERMARK_BADGES,
        "product_name": "Hibs Racing Intelligence",
        "product_tagline": "AI place-ranking · daily value sheet · verified paper ledger",
        "analytics_mode": True,
        "ranker_loaded": ranker_path.exists() and ranker_path.stat().st_size > 0,
    }
