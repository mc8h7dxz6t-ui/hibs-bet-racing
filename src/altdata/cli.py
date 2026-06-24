"""Alt-Data CLI — poll, check, export, verify-bundle."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from altdata.feeds import PRODUCTION_FEEDS, fetch_production_context, list_production_feeds
from altdata.ladders import default_fetchers, fetch_url_context, http_fetchers
from altdata.poll import poll_once
from altdata.resolver import FieldResolver
from inst_spine.cli_util import run_cli
from inst_spine.errors import CoverageError
from inst_spine.product_cli import (
    print_json,
    run_f9_check,
    run_institutional_export,
    run_institutional_verify,
)

PRODUCT = "altdata"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="altdata")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_poll = sub.add_parser("poll", help="Run one poll cycle")
    p_poll.add_argument("--feed", default="demo_feed")
    p_poll.add_argument("--url", default=None, help="HTTP(S) URL to fetch (enables live fetchers)")
    p_poll.add_argument(
        "--production-feed",
        default=None,
        choices=sorted(PRODUCTION_FEEDS.keys()),
        help="Registered production feed (real HTTP URL + field map)",
    )
    p_poll.add_argument("--timeout", type=float, default=10.0)
    p_poll.add_argument("--database", type=Path, default=Path("data/altdata_demo.sqlite"))
    p_poll.add_argument("--min-coverage", type=float, default=85.0)
    p_poll.add_argument("--ctx", default="{}", help="Extra context JSON merged after URL fetch")

    p_check = sub.add_parser("check", help="F1–F9 institutional check + coverage floor")
    p_check.add_argument("--database", type=Path, required=True)
    p_check.add_argument("--min-coverage", type=float, default=85.0)

    p_export = sub.add_parser("export", help="Deterministic audit bundle")
    p_export.add_argument("--database", type=Path, required=True)
    p_export.add_argument("--out-dir", type=Path, default=None)
    p_export.add_argument("--tarball", type=Path, default=None)
    p_export.add_argument("--repro-check", action="store_true")

    p_bundle = sub.add_parser("verify-bundle", help="Offline auditor replay")
    p_bundle.add_argument("--tarball", type=Path, required=True)
    p_bundle.add_argument("--anchor", type=Path, default=None)

    p_feeds = sub.add_parser("list-feeds", help="List registered production feeds")

    p_serve = sub.add_parser("serve", help="Secured feed read API")
    p_serve.add_argument("--host", default=None)
    p_serve.add_argument("--port", type=int, default=None)

    args = parser.parse_args(argv)

    if args.cmd == "list-feeds":
        print_json({"feeds": list_production_feeds(), "product": PRODUCT})
        return 0

    if args.cmd == "poll":
        ctx = json.loads(args.ctx)
        fetchers = default_fetchers()
        if args.production_feed:
            ctx = {**fetch_production_context(args.production_feed, timeout=args.timeout), **ctx}
            fetchers = http_fetchers()
        elif args.url:
            ctx = {**fetch_url_context(args.url, timeout=args.timeout), **ctx}
            fetchers = http_fetchers()
        result = poll_once(
            feed_id=args.feed,
            ctx=ctx,
            database=args.database,
            resolver=FieldResolver(fetchers=fetchers),
        )
        print_json({**result.__dict__, "product": PRODUCT})
        if result.coverage_pct < args.min_coverage:
            raise CoverageError(
                f"coverage {result.coverage_pct:.1f}% below floor {args.min_coverage:.1f}%",
                coverage_pct=result.coverage_pct,
            )
        return 0 if result.ok else 1

    if args.cmd == "check":
        code, body = run_f9_check(
            args.database,
            extra_context={"min_source_coverage_pct": args.min_coverage},
        )
        print_json(body)
        return code

    if args.cmd == "export":
        code, body = run_institutional_export(
            args.database,
            product=PRODUCT,
            out_dir=args.out_dir,
            tarball=args.tarball,
            repro_check=args.repro_check,
        )
        print_json(body)
        return code

    if args.cmd == "verify-bundle":
        code, body = run_institutional_verify(args.tarball, product=PRODUCT, anchor=args.anchor)
        print_json(body)
        return code

    if args.cmd == "serve":
        import os

        from altdata.serve import main as serve_main

        if args.host:
            os.environ["ALTDATA_HOST"] = args.host
        if args.port:
            os.environ["ALTDATA_PORT"] = str(args.port)
        serve_main()
        return 0

    return 1


if __name__ == "__main__":
    run_cli(lambda: main())
