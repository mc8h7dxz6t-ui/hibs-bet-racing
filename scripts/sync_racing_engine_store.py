#!/usr/bin/env python3
"""Automation: materialize engine_runner_features from scored cards."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    from hibs_racing.features.engine_runner_store import sync_racing_engine_store_from_scored_cards

    out = sync_racing_engine_store_from_scored_cards()
    log_dir = Path(os.getenv("LOG_DIR", "/var/log/hibs-racing"))
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / "racing-engine-store.json").write_text(
            json.dumps(out, indent=2, default=str) + "\n",
            encoding="utf-8",
        )
    except OSError:
        pass
    print(json.dumps(out, indent=2, default=str))
    return 0 if out.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
