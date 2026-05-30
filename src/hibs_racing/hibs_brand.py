"""Hibernian FC heritage badge assets — shared visual language with hibs-bet."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

HIBS_BADGE_PRIMARY = "logo_hibs_racing.svg"
HIBS_BADGE_HARP = "badge_harp_embroidered.png"
HIBS_HERO_HORSE = "hero_horse.png"

HIBS_HERITAGE_BADGES: list[dict[str, Any]] = [
    {"file": HIBS_BADGE_HARP, "label": "Golden harp shield", "era": "heritage"},
]

HIBS_WATERMARK_BADGES: list[str] = [HIBS_BADGE_HARP]


def hibs_brand_context() -> dict[str, Any]:
    bet_base = os.environ.get("HIBS_BET_BASE_URL", "http://127.0.0.1:5001").rstrip("/")
    ranker_path = Path(__file__).resolve().parents[2] / "data" / "models" / "lgbm_ranker.txt"
    return {
        "hibs_badge_primary": HIBS_BADGE_PRIMARY,
        "hibs_badge_harp": HIBS_BADGE_HARP,
        "hibs_hero_horse": HIBS_HERO_HORSE,
        "hibs_heritage_badges": HIBS_HERITAGE_BADGES,
        "hibs_watermark_badges": HIBS_WATERMARK_BADGES,
        "product_name": "hibs-racing",
        "product_tagline": "Edinburgh Racing Intelligence · ESTD 2026",
        "hibs_bet_url": bet_base,
        "ranker_loaded": ranker_path.exists() and ranker_path.stat().st_size > 0,
    }
