"""Alt-Data CLI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from altdata.poll import poll_once
from inst_spine.ledger import AppendOnlyLedger


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="altdata")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_poll = sub.add_parser("poll", help="Run one poll cycle")
    p_poll.add_argument("--feed", default="demo_feed")
    p_poll.add_argument("--ctx", default="{}", help="Context JSON for stub fetchers")
    p_poll.add_argument("--database", type=Path)

    p_check = sub.add_parser("check", help="Coverage + chain check")
    p_check.add_argument("--database", type=Path, required=True)
    p_check.add_argument("--min-coverage", type=float, default=85.0)

    args = parser.parse_args(argv)

    if args.cmd == "poll":
        ctx = json.loads(args.ctx)
        result = poll_once(feed_id=args.feed, ctx=ctx, database=args.database)
        print(json.dumps(result.__dict__, indent=2, default=str))
        return 0 if result.ok else 1

    if args.cmd == "check":
        ledger = AppendOnlyLedger(args.database)
        verify = ledger.verify()
        entries = ledger.list_entries()
        coverages = [
            (e.get("metadata") or {}).get("coverage_pct")
            for e in entries
            if (e.get("metadata") or {}).get("coverage_pct") is not None
        ]
        avg_cov = sum(coverages) / len(coverages) if coverages else 0.0
        out = {"verify": verify, "avg_coverage_pct": avg_cov, "entries": len(entries)}
        print(json.dumps(out, indent=2))
        ok = verify.get("chain_ok") and avg_cov >= args.min_coverage
        return 0 if ok else 1

    return 1


if __name__ == "__main__":
    sys.exit(main())
