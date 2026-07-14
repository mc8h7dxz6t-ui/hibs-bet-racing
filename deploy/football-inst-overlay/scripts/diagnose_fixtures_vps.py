#!/usr/bin/env python3
"""VPS fixture diagnostic — cache path, scrape sources, bundle count."""

from __future__ import annotations

import glob
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.chdir(ROOT)

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")


def _key_ok(name: str, min_len: int = 8) -> str:
    v = (os.getenv(name) or "").strip()
    return "OK" if len(v) >= min_len else "MISSING"


def main() -> int:
    from hibs_predictor.cache import Cache, default_cache_dir
    from hibs_predictor.scrape_first import scrape_first_status
    from hibs_predictor.tournament_focus import active_competition_league_codes
    from hibs_predictor.web import _all_fixtures_cache_key, fetch_next_48h_fixtures

    cache_dir = Path(default_cache_dir())
    if not cache_dir.is_absolute():
        cache_dir = ROOT / cache_dir

    ck = _all_fixtures_cache_key(include_domestic=False)
    peek = Cache(cache_dir=str(cache_dir)).peek(ck)
    bundle_n = len((peek or {}).get("all") or []) if isinstance(peek, dict) else 0

    print("=== hibs-bet fixture diagnostic ===")
    print(f"HOME={os.getenv('HOME', '')}")
    print(f"HIBS_CACHE_DIR={os.getenv('HIBS_CACHE_DIR', '(unset → .cache)')}")
    print(f"cache_dir={cache_dir}")
    print(f"bundle_key={ck}")
    print(f"bundle_fixtures={bundle_n}")
    print(f"FOOTBALL_DATA_ORG_KEY={_key_ok('FOOTBALL_DATA_ORG_KEY')}")
    print(f"scrape_first={json.dumps(scrape_first_status())}")

    patterns = sorted(glob.glob(str(cache_dir / "all_fixtures*.json")))
    print(f"all_fixtures_cache_files={len(patterns)}")
    for p in patterns[:5]:
        print(f"  {Path(p).name}")

    leagues = list(active_competition_league_codes())[:8]
    print(f"active_leagues(sample)={leagues}")
    print("--- per-league scrape fetch (next window) ---")
    total = 0
    for code in leagues:
        try:
            rows = fetch_next_48h_fixtures(code, allow_stale=True)
            n = len(rows or [])
            total += n
            src = (rows[0].get("source") if rows else None) or "-"
            print(f"  {code}: {n} (sample_source={src})")
        except Exception as exc:
            print(f"  {code}: ERROR {exc!r}")
    print(f"scrape_fetch_total={total}")
    print(f"fixtures: {bundle_n if bundle_n else total}")
    return 0 if (bundle_n or total) else 2


if __name__ == "__main__":
    raise SystemExit(main())
