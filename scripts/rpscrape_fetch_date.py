#!/usr/bin/env python3
"""Fetch rpscrape racecards for an absolute calendar date (YYYY-MM-DD)."""

from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from pathlib import Path

# Vendor rpscrape scripts on path
ROOT = Path(__file__).resolve().parents[1]
VENDOR_SCRIPTS = ROOT / "vendor" / "rpscrape" / "scripts"
sys.path.insert(0, str(VENDOR_SCRIPTS))

from dotenv import load_dotenv  # noqa: E402
from orjson import dumps  # noqa: E402
from utils.network import NetworkClient  # noqa: E402
from utils.region import valid_region  # noqa: E402

from racecards import get_meetings, load_field_config, scrape_racecards  # noqa: E402

load_dotenv(ROOT / ".env")
load_dotenv(VENDOR_SCRIPTS.parent / ".env")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch RP racecards for one calendar date.")
    parser.add_argument("--date", required=True, help="Card date YYYY-MM-DD")
    parser.add_argument("--region", default=None, help="gb | ire (default: both via None)")
    args = parser.parse_args()

    card_date = args.date.strip()
    region = args.region.lower() if args.region else None
    if region and not valid_region(region):
        print(f"Invalid region: {args.region}", file=sys.stderr)
        return 1

    config = load_field_config()
    client = NetworkClient(
        email=os.getenv("EMAIL"),
        access_token=os.getenv("ACCESS_TOKEN"),
    )
    meetings = get_meetings(client, [card_date], region)
    if card_date not in meetings or not meetings[card_date]:
        print(f"No meetings for {card_date}", file=sys.stderr)
        return 2

    racecards = scrape_racecards(meetings[card_date], card_date, config, client)
    out_dir = VENDOR_SCRIPTS.parent / "racecards"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{card_date}.json"
    out_path.write_text(dumps(racecards).decode("utf-8"), encoding="utf-8")
    print(str(out_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
