from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from hibs_racing.backtest.place_signal import run_place_backtest
from hibs_racing.config import db_path, load_config
from hibs_racing.features.build_features import build_next_run_outcomes, build_tags
from hibs_racing.features.store import init_db
from hibs_racing.ingest.backfill import export_parquet_year, ingest_csv


def cmd_init(_: argparse.Namespace) -> int:
    cfg = load_config()
    init_db(db_path(cfg))
    print(f"Initialized {db_path(cfg)}")
    return 0


def cmd_ingest(args: argparse.Namespace) -> int:
    path = Path(args.csv)
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        return 1
    n = ingest_csv(path, skip_if_seen=not args.force)
    print(f"Ingested {n} rows from {path.name}")
    if args.parquet:
        out = export_parquet_year(path)
        print(f"Parquet archive: {out}")
    return 0


def cmd_tag(args: argparse.Namespace) -> int:
    stats = build_tags(use_spacy=getattr(args, "spacy", False))
    print(json.dumps(stats, indent=2))
    return 0


def cmd_parse(args: argparse.Namespace) -> int:
    from hibs_racing.nlp.pipeline import parse_comment

    features = parse_comment(args.comment, use_spacy=args.spacy)
    print(json.dumps(features.as_dict(), indent=2))
    return 0


def cmd_outcomes(_: argparse.Namespace) -> int:
    n = build_next_run_outcomes()
    print(f"Built {n} next-run outcome rows")
    return 0


def cmd_backtest(_: argparse.Namespace) -> int:
    report = run_place_backtest()
    print(json.dumps(report.to_dict(), indent=2))
    return 0


def cmd_scrape(args: argparse.Namespace) -> int:
    from datetime import date as date_cls, timedelta

    import pandas as pd

    from hibs_racing.config import data_dir
    from hibs_racing.ingest.rpscrape_adapter import normalize_rpscrape_files
    from hibs_racing.ingest.scrape import (
        collect_all_valid_csvs,
        collect_valid_csvs_in_range,
        run_rpscrape,
    )

    if args.date:
        parts = args.date.replace("-", "/").split("/")
        if len(parts) != 3:
            print("Use --date YYYY/MM/DD or YYYY-MM-DD", file=sys.stderr)
            return 1
        end = date_cls(int(parts[0]), int(parts[1]), int(parts[2]))
        start = end - timedelta(days=max(args.days, 1) - 1)
    else:
        end = date_cls.today() - timedelta(days=1)
        start = end - timedelta(days=max(args.days, 1) - 1)

    print(f"Scrape range: {start.isoformat()} → {end.isoformat()} ({args.days} days, 1 day per job)")

    if args.from_cache:
        raw_files = collect_all_valid_csvs(args.region, args.type)
        if not raw_files:
            print("No valid cached CSVs found under vendor/rpscrape/data/", file=sys.stderr)
            return 1
        print(f"Using {len(raw_files)} cached file(s) — no network scrape")
    else:
        print(
            f"Live scrape (timeout {90}s per day). If RP blocks, pipeline falls back to cache.\n"
            "Skip network entirely: hibs-racing scrape --from-cache --pipeline"
        )
        try:
            run_rpscrape(
                start=start,
                end=end,
                region=args.region,
                race_type=args.type,
                clean=args.clean,
                chunk_days=1,
                pause_seconds=3.0,
                max_retries=0,
            )
        except RuntimeError as exc:
            print(str(exc))
        raw_files = collect_valid_csvs_in_range(start, end, region=args.region, race_type=args.type)
        if not raw_files:
            cached = collect_all_valid_csvs(args.region, args.type)
            if cached:
                print("Falling back to cached CSV files on disk (live scrape failed or rate-limited).")
                raw_files = cached
            else:
                print("No cached data. Run earlier successful scrape or use --from-cache after backfill.", file=sys.stderr)
                return 1

    print(f"Scraped {len(raw_files)} file(s) from Racing Post via rpscrape")
    for path in raw_files:
        print(f"  {path}")

    out_dir = data_dir() / "raw"
    merged = normalize_rpscrape_files(raw_files, output_dir=out_dir)
    row_count = len(pd.read_csv(merged))
    print(f"Normalized → {merged} ({row_count} runners with comments)")

    if args.ingest or args.pipeline:
        rc = cmd_ingest(argparse.Namespace(csv=str(merged), force=True, parquet=False))
        if rc:
            return rc
    if args.pipeline:
        cmd_tag(args)
        cmd_outcomes(args)
        return cmd_backtest(args)
    return 0


def cmd_ingest_raceform(args: argparse.Namespace) -> int:
    from hibs_racing.ingest.raceform_db import ingest_raceform_db

    path = Path(args.db)
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        return 1

    stats = ingest_raceform_db(
        path,
        since=args.since,
        until=args.until,
        year=args.year,
        limit=args.limit,
    )
    print(json.dumps(stats, indent=2))

    if args.pipeline:
        cmd_tag(args)
        cmd_outcomes(args)
        from hibs_racing.features.ranker_matrix import build_ranker_matrix

        build_ranker_matrix()
        print(json.dumps({"matrix": "built"}, indent=2))
        if args.backtest:
            return cmd_backtest(args)
    elif getattr(args, "sync", False):
        cmd_tag(args)
        cmd_outcomes(args)
        print(json.dumps({"sync": "tag + outcomes complete"}, indent=2))
    return 0


def cmd_build_matrix(_: argparse.Namespace) -> int:
    from hibs_racing.features.ranker_matrix import build_ranker_matrix

    frame = build_ranker_matrix()
    print(
        json.dumps(
            {
                "rows": len(frame),
                "races": int(frame["race_id"].nunique()) if not frame.empty else 0,
                "parquet": str(Path(load_config()["paths"]["parquet_dir"]) / "ranker_matrix.parquet"),
            },
            indent=2,
        )
    )
    return 0


def cmd_train_ranker(_: argparse.Namespace) -> int:
    from hibs_racing.models.lgbm_ranker import train_lgbm_ranker

    try:
        report = train_lgbm_ranker()
    except ImportError as exc:
        print(json.dumps({"message": str(exc)}, indent=2))
        return 1
    print(json.dumps(report.to_dict(), indent=2))
    return 0


def cmd_feature_importance(args: argparse.Namespace) -> int:
    from hibs_racing.models.feature_importance import print_feature_importance_report

    try:
        print_feature_importance_report(as_json=args.json)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


def cmd_poll_odds(args: argparse.Namespace) -> int:
    from hibs_racing.odds.market_steam import poll_matchbook_odds_once, run_matchbook_poll_loop

    if args.once:
        report = poll_matchbook_odds_once()
        print(json.dumps(report.to_dict(), indent=2))
        return 0 if not report.errors or report.runners_priced > 0 else 1
    run_matchbook_poll_loop(interval_seconds=args.interval, max_cycles=args.max_cycles)
    return 0


def cmd_route_execution(args: argparse.Namespace) -> int:
    from hibs_racing.cards.query import load_scored_cards
    from hibs_racing.live.execution_router import build_execution_intents, route_execution_batch

    scored = load_scored_cards()
    intents = build_execution_intents(scored)
    report = route_execution_batch(intents, log_results=True)
    print(json.dumps(report, indent=2))
    return 0


def cmd_refresh_cards(args: argparse.Namespace) -> int:
    """Same path as web Refresh 24h: GB+IRE window, score, optional odds + paper."""
    from hibs_racing.cards.refresh import refresh_cards

    window = getattr(args, "window", 24)
    window_hours = int(window) if window is not None else 24
    if getattr(args, "no_window", False):
        window_hours = None

    try:
        stats = refresh_cards(
            source=args.source,
            region=args.region,
            day=args.day,
            odds_source=args.odds_source,
            window_hours=window_hours,
            regions=tuple(r.strip().lower() for r in args.regions.split(",") if r.strip()),
            paper=args.paper,
            parallel_workers=getattr(args, "workers", None),
        )
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, **stats}, indent=2))
    return 0


def cmd_fetch_cards(args: argparse.Namespace) -> int:
    from hibs_racing.cards.store import store_upcoming_runners
    from hibs_racing.ingest.racecards import load_racecard_frames, parse_racecard_json
    from hibs_racing.ingest.racing_api import fetch_racing_api_racecards

    try:
        if args.source == "racing_api":
            frame = fetch_racing_api_racecards(
                day=None if args.days else args.day,
                days=args.days,
                region=args.region,
            )
            source = "racing_api"
        else:
            from hibs_racing.ingest.racecards import load_racecard_frames

            frame = load_racecard_frames(day=None if args.days else args.day, days=args.days, region=args.region)
            source = "rpscrape"
            print(f"Racecards: {int(frame['card_date'].nunique())} day(s), {len(frame)} runners")
    except Exception as exc:
        print(f"Fetch failed: {exc}", file=sys.stderr)
        print("Fallback: hibs-racing ingest-cards data/samples/cards_template.csv", file=sys.stderr)
        return 1

    n = store_upcoming_runners(frame, source=source)
    print(json.dumps({"runners": n, "races": int(frame["race_id"].nunique()), "source": source}, indent=2))
    if args.score:
        return cmd_score_card(
            argparse.Namespace(
                odds=args.odds,
                odds_source=getattr(args, "odds_source", None),
                race_urls=getattr(args, "race_urls", None),
                paper=args.paper,
                top=args.top,
            )
        )
    return 0


def cmd_ingest_cards(args: argparse.Namespace) -> int:
    from hibs_racing.cards.store import store_upcoming_runners
    from hibs_racing.ingest.racecards import normalize_cards_csv, parse_racecard_json

    path = Path(args.path)
    if not path.exists():
        print(f"Not found: {path}", file=sys.stderr)
        return 1
    if path.suffix.lower() == ".json":
        frame = parse_racecard_json(path)
        source = "json"
    else:
        import pandas as pd

        frame = normalize_cards_csv(pd.read_csv(path))
        source = "csv"
    n = store_upcoming_runners(frame, source=source)
    print(json.dumps({"runners": n, "source": source}, indent=2))
    if args.score:
        return cmd_score_card(
            argparse.Namespace(
                odds=args.odds,
                odds_source=getattr(args, "odds_source", None),
                race_urls=getattr(args, "race_urls", None),
                paper=args.paper,
                top=args.top,
            )
        )
    return 0


def cmd_score_card(args: argparse.Namespace) -> int:
    import pandas as pd

    from hibs_racing.cards.score_card import paper_log_value_picks, score_upcoming_cards, top_place_picks
    from hibs_racing.cards.store import load_upcoming_runners
    from hibs_racing.odds.loader import resolve_scoring_odds

    cards = load_upcoming_runners()
    if cards.empty:
        print("No upcoming cards — run fetch-cards or ingest-cards first.", file=sys.stderr)
        return 1

    odds, meta = resolve_scoring_odds(
        cards,
        odds_csv=getattr(args, "odds", None),
        odds_source=getattr(args, "odds_source", None),
        race_urls_file=getattr(args, "race_urls", None),
    )
    if meta.get("report"):
        print(json.dumps(meta["report"], indent=2), file=sys.stderr)
    if odds is not None and not odds.empty:
        print(f"Odds source: {meta.get('source')} ({len(odds)} prices)", file=sys.stderr)
    elif meta.get("source") == "none":
        print("No odds loaded — EW value flags will be empty.", file=sys.stderr)

    scored = score_upcoming_cards(cards, odds=odds)
    picks = top_place_picks(scored, per_race=args.top)
    print("=== Top place angles (combo + NLP) ===")
    print(picks.to_string(index=False))

    value = scored[scored["value_flag"] == 1]
    if not value.empty:
        print("\n=== Value EW flags (place EV + combo gate) ===")
        show = value[
            [
                c
                for c in (
                    "course",
                    "off_time",
                    "horse_name",
                    "jockey",
                    "trainer",
                    "model_place_prob",
                    "combo_bayes_place",
                    "place_ev",
                    "ew_combined_ev",
                )
                if c in value.columns
            ]
        ]
        print(show.to_string(index=False))

    if args.paper and not value.empty:
        ids = paper_log_value_picks(value, stake=float(load_config().get("paper", {}).get("default_stake", 1.0)))
        print(f"\nPaper bets logged: {len(ids)}")

    out = Path(load_config()["paths"]["parquet_dir"]) / "card_scores.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    scored.to_parquet(out, index=False)
    print(f"\nFull scores: {out}")
    return 0


def cmd_fetch_odds(args: argparse.Namespace) -> int:
    from hibs_racing.cards.store import load_upcoming_runners
    from hibs_racing.odds.matchbook import fetch_matchbook_odds
    from hibs_racing.odds.oddschecker import fetch_oddschecker_odds, load_race_urls_file

    cards = load_upcoming_runners()
    if cards.empty:
        print("No upcoming cards — run fetch-cards first.", file=sys.stderr)
        return 1

    source = getattr(args, "source", "oddschecker") or "oddschecker"
    race_urls = load_race_urls_file(Path(args.race_urls)) if getattr(args, "race_urls", None) else {}

    if source in ("matchbook", "mb", "exchange"):
        odds, report = fetch_matchbook_odds(cards)
        default_name = "matchbook_odds.parquet"
    else:
        odds, report = fetch_oddschecker_odds(cards, race_urls=race_urls)
        default_name = "retail_odds.parquet"

    out = Path(args.out) if args.out else Path(load_config()["paths"]["parquet_dir"]) / default_name
    out.parent.mkdir(parents=True, exist_ok=True)
    odds.to_parquet(out, index=False)
    print(json.dumps({"output": str(out), "source": source, **report.to_dict()}, indent=2))
    return 0 if report.runners_priced > 0 else 1


def cmd_settle_paper(_: argparse.Namespace) -> int:
    from hibs_racing.place.paper_ledger import settle_paper_bets

    result = settle_paper_bets()
    print(json.dumps(result, indent=2))
    return 0


def cmd_monitor(args: argparse.Namespace) -> int:
    from hibs_racing.monitor import run_monitor_cycle

    if args.loop and args.loop > 0:
        import time

        while True:
            snap = run_monitor_cycle(refresh=args.refresh)
            print(json.dumps(snap, indent=2, default=str))
            time.sleep(args.loop)
    snap = run_monitor_cycle(refresh=args.refresh)
    print(json.dumps(snap, indent=2, default=str))
    return 0


def cmd_settle_tips(_: argparse.Namespace) -> int:
    from hibs_racing.features.store import connect
    from hibs_racing.tips.settle import settle_matched_tips
    from hibs_racing.tips.store import ensure_tipster_schema, tipster_summary

    db = db_path(load_config())
    ensure_tipster_schema(db)
    with connect(db) as conn:
        n = settle_matched_tips(conn)
        conn.commit()
    print(json.dumps({"settled": n, "summary": tipster_summary(db)}, indent=2))
    return 0


def cmd_ingest_tips(args: argparse.Namespace) -> int:
    from hibs_racing.tips.ingest import (
        ingest_from_imap,
        ingest_pasted_text,
        ingest_tip_paths,
        _collect_paths,
    )

    if getattr(args, "imap", False):
        try:
            result = ingest_from_imap(match=not args.no_match, settle=args.settle)
        except Exception as exc:
            print(str(exc), file=sys.stderr)
            return 1
        _print_tip_ingest_result(result, json_out=args.json, label="IMAP")
        return 0

    if args.paste or args.path == "-":
        text = sys.stdin.read()
        if not text.strip():
            print("No paste text on stdin", file=sys.stderr)
            return 1
        result = ingest_pasted_text(
            text,
            default_date=args.date,
            match=not args.no_match,
            settle=args.settle,
        )
        _print_tip_ingest_result(result, json_out=args.json, label="paste")
        return 0

    path = Path(args.path)
    if not path.exists():
        print(f"Not found: {path}", file=sys.stderr)
        return 1
    files = _collect_paths(path)
    if not files:
        print(f"No .eml/.txt files in {path}", file=sys.stderr)
        return 1
    result = ingest_tip_paths(
        files,
        default_date=args.date,
        match=not args.no_match,
        settle=args.settle,
    )
    _print_tip_ingest_result(result, json_out=args.json, label="files")
    return 0


def _print_tip_ingest_result(result: dict, *, json_out: bool, label: str) -> None:
    if json_out:
        print(json.dumps(result, indent=2))
        return
    if label == "IMAP":
        print(f"Fetched {result.get('emails_fetched', 0)} email(s) from inbox")
    elif label == "paste":
        print(f"Parsed {result.get('chunks', 1)} paste chunk(s)")
    else:
        print(
            f"Ingested {result['inserted']} tips from {result.get('files', 0)} file(s) "
            f"({result['skipped_duplicate']} duplicates skipped, {result['tips_found']} parsed lines)"
        )
    if result.get("summary"):
        s = result["summary"]
        print(
            f"Ledger: {s['total_tips']} total, {s['settled']} settled, "
            f"win {s['win_pct'] or '—'}%, place {s['place_pct'] or '—'}% | "
            f"non-stable win {s['non_stable_win_pct'] or '—'}%"
        )
    for r in result.get("results", []):
        for t in r.get("tips", []):
            flag = "★ stable" if t.get("stable_intel") == "yes" else ""
            print(
                f"  · {t.get('horse_name') or '?'} @ {t.get('course') or '?'} "
                f"{t.get('off_time') or ''} {t.get('odds_quoted') or ''} "
                f"[{t.get('match_status')}] {flag}".rstrip()
            )


def cmd_fetch_tips(args: argparse.Namespace) -> int:
    args.imap = True
    args.paste = False
    args.path = ""
    return cmd_ingest_tips(args)


def cmd_web(args: argparse.Namespace) -> int:
    try:
        from hibs_racing.web import main as web_main
    except ImportError as exc:
        print("Install web extra: pip install -e '.[web]'", file=sys.stderr)
        print(str(exc), file=sys.stderr)
        return 1
    if args.port:
        os.environ["PORT"] = str(args.port)
    if args.host:
        os.environ["HOST"] = args.host
    web_main()
    return 0


def cmd_phase_a(args: argparse.Namespace) -> int:
    """Full Phase A pipeline: init → ingest → tag → outcomes → backtest."""
    cmd_init(args)
    if args.csv:
        rc = cmd_ingest(args)
        if rc:
            return rc
    cmd_tag(args)
    cmd_outcomes(args)
    return cmd_backtest(args)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hibs-racing", description="Offline racing research CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Create SQLite feature store")
    p_init.set_defaults(func=cmd_init)

    p_ingest = sub.add_parser("ingest", help="Ingest results CSV (idempotent)")
    p_ingest.add_argument("csv", help="Path to results CSV with comments")
    p_ingest.add_argument("--parquet", action="store_true", help="Also write year Parquet archive")
    p_ingest.add_argument("--force", action="store_true", help="Re-ingest even if file hash seen")
    p_ingest.set_defaults(func=cmd_ingest)

    p_raceform = sub.add_parser("ingest-raceform", help="Bulk ingest Kaggle raceform.db")
    p_raceform.add_argument("db", help="Path to raceform.db")
    p_raceform.add_argument("--year", type=int, help="Ingest one year only e.g. 2026")
    p_raceform.add_argument("--since", help="Start date YYYY-MM-DD")
    p_raceform.add_argument("--until", help="End date YYYY-MM-DD")
    p_raceform.add_argument("--limit", type=int, help="Max rows (testing)")
    p_raceform.add_argument("--pipeline", action="store_true", help="tag + outcomes + build-matrix")
    p_raceform.add_argument("--sync", action="store_true", help="tag + outcomes only (daily refresh — no matrix rebuild)")
    p_raceform.add_argument("--backtest", action="store_true", help="Also run backtest (with --pipeline)")
    p_raceform.add_argument("--spacy", action="store_true")
    p_raceform.set_defaults(func=cmd_ingest_raceform)

    p_tag = sub.add_parser("tag", help="Run sectional NLP tagger over ingested comments")
    p_tag.add_argument("--spacy", action="store_true", help="Merge spaCy PhraseMatcher (optional)")
    p_tag.set_defaults(func=cmd_tag)

    p_parse = sub.add_parser("parse", help="Parse one running comment → sectional proxy features")
    p_parse.add_argument("comment", help="Running comment text")
    p_parse.add_argument("--spacy", action="store_true", help="Merge spaCy PhraseMatcher (optional)")
    p_parse.set_defaults(func=cmd_parse)

    p_out = sub.add_parser("outcomes", help="Build next-run place labels")
    p_out.set_defaults(func=cmd_outcomes)

    p_bt = sub.add_parser("backtest", help="Place/top-N signal backtest")
    p_bt.set_defaults(func=cmd_backtest)

    p_matrix = sub.add_parser("build-matrix", help="Build LTR feature matrix (combo + NLP + relative)")
    p_matrix.set_defaults(func=cmd_build_matrix)

    p_ranker = sub.add_parser("train-ranker", help="Train LightGBM LambdaRank (needs .[ranker] extra)")
    p_ranker.set_defaults(func=cmd_train_ranker)

    p_fi = sub.add_parser("feature-importance", help="Feature importance matrix + holdout AUC diagnostic")
    p_fi.add_argument("--json", action="store_true", help="Output JSON")
    p_fi.set_defaults(func=cmd_feature_importance)

    p_poll = sub.add_parser("poll-odds", help="Matchbook steam/drift polling loop (default 120s)")
    p_poll.add_argument("--once", action="store_true", help="Single poll cycle")
    p_poll.add_argument("--interval", type=int, default=120, help="Seconds between polls")
    p_poll.add_argument("--max-cycles", type=int, help="Stop after N cycles (default: infinite)")
    p_poll.set_defaults(func=cmd_poll_odds)

    p_fc = sub.add_parser("fetch-cards", help="Fetch upcoming racecards (rpscrape or Racing API)")
    p_fc.add_argument("--day", type=int, default=1, help="Single day: 1=today, 2=tomorrow")
    p_fc.add_argument(
        "--days",
        type=int,
        help="Range: 1=today only, 2=today+tomorrow (rpscrape --days N)",
    )
    p_fc.add_argument("--region", default="gb")
    p_fc.add_argument("--source", choices=["rpscrape", "racing_api"], default="rpscrape")
    p_fc.add_argument("--score", action="store_true", help="Score immediately after fetch")
    p_fc.add_argument("--odds", help="Optional odds CSV for EW value")
    p_fc.add_argument(
        "--odds-source",
        choices=["auto", "matchbook", "oddschecker", "csv", "none"],
        help="Odds source when --score (default: auto)",
    )
    p_fc.add_argument("--race-urls", help="JSON map race_id→Oddschecker URL (bypass search)")
    p_fc.add_argument("--paper", action="store_true", help="Log paper EW bets for value flags")
    p_fc.add_argument("--top", type=int, default=2, help="Top N per race to display")
    p_fc.set_defaults(func=cmd_fetch_cards)

    p_refresh = sub.add_parser(
        "refresh-cards",
        help="Fetch next 24h GB+IRE cards, score with ranker, pull odds (same as web Refresh 24h)",
    )
    p_refresh.add_argument("--source", choices=["rpscrape", "racing_api"], default="racing_api")
    p_refresh.add_argument("--region", default="gb", help="Used only when --no-window")
    p_refresh.add_argument("--day", type=int, default=1, help="Used only when --no-window")
    p_refresh.add_argument("--window", type=int, default=24, help="Hours ahead to keep (default 24)")
    p_refresh.add_argument("--no-window", action="store_true", help="Single region/day fetch instead of 24h window")
    p_refresh.add_argument("--regions", default="gb,ire", help="Comma-separated regions for window mode")
    p_refresh.add_argument(
        "--odds-source",
        choices=["auto", "matchbook", "oddschecker", "csv", "none"],
        default="auto",
    )
    p_refresh.add_argument("--paper", action="store_true", help="Log paper EW bets for value flags")
    p_refresh.add_argument("--workers", type=int, help="Parallel workers for fetch + RP verdict (default: config)")
    p_refresh.set_defaults(func=cmd_refresh_cards)

    p_exec = sub.add_parser(
        "route-execution",
        help="Preview automated Matchbook/Betfair routing for value picks (dry-run by default)",
    )
    p_exec.set_defaults(func=cmd_route_execution)

    p_ic = sub.add_parser("ingest-cards", help="Load racecards from CSV or rpscrape JSON")
    p_ic.add_argument("path", help="cards.csv or YYYY-MM-DD.json")
    p_ic.add_argument("--score", action="store_true")
    p_ic.add_argument("--odds", help="Optional odds CSV")
    p_ic.add_argument("--paper", action="store_true")
    p_ic.add_argument("--top", type=int, default=2)
    p_ic.set_defaults(func=cmd_ingest_cards)

    p_sc = sub.add_parser("score-card", help="Score upcoming cards → place probs → optional EW value")
    p_sc.add_argument("--odds", help="CSV: horse_name or runner_id, win_decimal, place_fraction, places")
    p_sc.add_argument(
        "--odds-source",
        choices=["auto", "matchbook", "oddschecker", "csv", "none"],
        help="auto=API prices→Matchbook→none; matchbook=exchange back prices",
    )
    p_sc.add_argument("--race-urls", help="JSON map race_id→Oddschecker URL")
    p_sc.add_argument("--paper", action="store_true", help="Log value picks to paper_bets table")
    p_sc.add_argument("--top", type=int, default=2, help="Top N place picks per race to print")
    p_sc.set_defaults(func=cmd_score_card)

    p_odds = sub.add_parser("fetch-odds", help="Fetch win prices (Matchbook or Oddschecker)")
    p_odds.add_argument(
        "--source",
        choices=["matchbook", "oddschecker"],
        default="oddschecker",
        help="Price source (default oddschecker retail)",
    )
    p_odds.add_argument("--out", help="Output parquet path")
    p_odds.add_argument("--race-urls", help="Oddschecker only: JSON race_id→URL map")
    p_odds.set_defaults(func=cmd_fetch_odds)

    p_web = sub.add_parser("web", help="Launch hibs-racing web UI (default port 5003)")
    p_web.add_argument("--port", type=int, default=5003)
    p_web.add_argument("--host", default="127.0.0.1")
    p_web.set_defaults(func=cmd_web)

    p_mon = sub.add_parser("monitor", help="Auto-monitor: top places + settle paper bets")
    p_mon.add_argument("--refresh", action="store_true", help="Fetch fresh card from API first")
    p_mon.add_argument("--loop", type=int, help="Repeat every N seconds")
    p_mon.set_defaults(func=cmd_monitor)

    p_settle = sub.add_parser("settle-paper", help="Settle open paper bets from ingested results")
    p_settle.set_defaults(func=cmd_settle_paper)

    p_tips = sub.add_parser("ingest-tips", help="Ingest tips: paste, .eml folder, or IMAP inbox")
    p_tips.add_argument(
        "path",
        nargs="?",
        default="-",
        help="File/folder, or '-' / omit with --paste for stdin (default: -)",
    )
    p_tips.add_argument("--paste", action="store_true", help="Read pasted email text from stdin")
    p_tips.add_argument("--imap", action="store_true", help="Fetch from IMAP inbox (TIPSTER_IMAP_* in .env)")
    p_tips.add_argument("--date", help="Default card date YYYY-MM-DD if missing from email")
    p_tips.add_argument("--settle", action="store_true", help="Settle matched tips from ingested results")
    p_tips.add_argument("--no-match", action="store_true", help="Skip matching tips to runners")
    p_tips.add_argument("--json", action="store_true", help="Print full JSON report")
    p_tips.set_defaults(func=cmd_ingest_tips, imap=False, paste=False)

    p_ft = sub.add_parser("fetch-tips", help="Pull new tip emails from IMAP inbox (alias for ingest-tips --imap)")
    p_ft.add_argument("--settle", action="store_true")
    p_ft.add_argument("--no-match", action="store_true")
    p_ft.add_argument("--json", action="store_true")
    p_ft.set_defaults(func=cmd_fetch_tips, imap=True, paste=False, path="", date=None)

    p_st = sub.add_parser("settle-tips", help="Settle matched tipster tips from results DB")
    p_st.set_defaults(func=cmd_settle_tips)

    p_scrape = sub.add_parser("scrape", help="Scrape GB/IRE results + comments (rpscrape)")
    p_scrape.add_argument("--days", type=int, default=7, help="Number of days to scrape (default 7)")
    p_scrape.add_argument(
        "--date",
        help="End date YYYY/MM/DD or YYYY-MM-DD (default: yesterday)",
    )
    p_scrape.add_argument("--region", default="gb", help="Region code: gb, ire, …")
    p_scrape.add_argument("--type", default="flat", dest="type", help="flat or jumps")
    p_scrape.add_argument(
        "--from-cache",
        action="store_true",
        help="Skip network; ingest valid CSVs already on disk",
    )
    p_scrape.add_argument("--clean", action="store_true", help="Clear rpscrape cache first")
    p_scrape.add_argument("--ingest", action="store_true", help="Ingest normalized CSV into SQLite")
    p_scrape.add_argument(
        "--pipeline",
        action="store_true",
        help="Scrape → ingest → tag → outcomes → backtest",
    )
    p_scrape.add_argument("--spacy", action="store_true")
    p_scrape.set_defaults(func=cmd_scrape)

    p_a = sub.add_parser("phase-a", help="Run full Phase A pipeline")
    p_a.add_argument("csv", nargs="?", help="Optional CSV to ingest first")
    p_a.add_argument("--parquet", action="store_true")
    p_a.add_argument("--force", action="store_true")
    p_a.add_argument("--spacy", action="store_true")
    p_a.set_defaults(func=cmd_phase_a)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
