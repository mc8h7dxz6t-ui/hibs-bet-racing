"""Feed schema registry — bundle extras for auditor field-ladder verification."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from altdata.ladders import FIELD_LADDERS


def feed_schema_registry() -> dict[str, Any]:
    return {
        "protocol": "inst-altdata-feed-schema-v1",
        "feeds": {
            feed_id: {
                "fields": list(ladder),
                "field_count": len(ladder),
            }
            for feed_id, ladder in FIELD_LADDERS.items()
        },
    }


def write_feed_schema_file(dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(feed_schema_registry(), indent=2, sort_keys=True), encoding="utf-8")
    return dest
