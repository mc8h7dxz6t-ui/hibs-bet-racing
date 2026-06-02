"""Hibs Racing Intelligence — brand assets (unified HIBS logo)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

HIBS_HARVESTED_LOGO = "hibs_harvested_logo.png"
HIBS_BADGE_PRIMARY = HIBS_HARVESTED_LOGO
HIBS_BADGE_HARP = HIBS_HARVESTED_LOGO
HIBS_RACING_LOGO = HIBS_HARVESTED_LOGO
HIBS_HERO_HORSE = "hero_horse.png"
HIBS_HORSE_CLUB_REF = "logo_horse_club_ref.png"

HIBS_HERITAGE_BADGES: list[dict[str, Any]] = [
    {"file": HIBS_HARVESTED_LOGO, "label": "HIBS — Harvested Intelligent Betting System", "era": "present"},
]

HIBS_WATERMARK_BADGES: list[str] = [HIBS_HARVESTED_LOGO]


def hibs_brand_context() -> dict[str, Any]:
    ranker_path = Path(__file__).resolve().parents[2] / "data" / "models" / "lgbm_ranker.txt"
    return {
        "hibs_badge_primary": HIBS_BADGE_PRIMARY,
        "hibs_badge_harp": HIBS_BADGE_HARP,
        "hibs_harvested_logo": HIBS_HARVESTED_LOGO,
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
