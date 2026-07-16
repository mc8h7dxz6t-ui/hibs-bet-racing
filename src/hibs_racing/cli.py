from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from hibs_racing.backtest.place_signal import run_place_backtest
from hibs_racing.backtest.retrospective import run_retrospective_backtest
from hibs_racing.config import db_path, load_config
from hibs_racing.features.build_features import build_next_run_outcomes, build_tags
from hibs_racing.features.store import init_db
from hibs_racing.ingest.backfill import export_parquet_year, ingest_csv


def _load_dotenv_if_present() -> None:
    """Load repo .env for CLI (matches web + daily_refresh.sh)."""
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.exists():
        return
    try:
        from dotenv import load_dotenv

        load_dotenv(env_path)
    except ImportError:
        pass


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


def cmd_compare_gates(args: argparse.Namespace) -> int:
    from hibs_racing.backtest.gate_compare import compare_value_gates

    report = compare_value_gates(days=int(getattr(args, "days", 14)))
    print(json.dumps(report.to_dict(), indent=2))
    return 0 if report.rows > 0 else 1


def cmd_benchmark_gates(args: argparse.Namespace) -> int:
    from hibs_racing.config import ROOT
    from hibs_racing.backtest.gate_benchmark import run_gate_benchmark, run_gate_benchmark_walkforward

    start = getattr(args, "start", None)
    end = getattr(args, "end", None)
    use_snapshots = not getattr(args, "no_snapshots", False)
    write_snapshots = getattr(args, "write_snapshots", False)
    snap_hash = getattr(args, "snapshot_config_hash", None)
    if getattr(args, "walkforward", False):
        out = getattr(args, "output", None) or (ROOT / "exports" / "gate_walkforward.json")
        progress = out.with_name("gate_walkforward_progress.json")
        report = run_gate_benchmark_walkforward(
            start=start,
            end=end,
            progress_path=progress,
            use_snapshots=use_snapshots,
            write_snapshots=write_snapshots,
            snapshot_config_hash=snap_hash,
        )
        payload = report.to_dict()
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        payload["output_path"] = str(out)
        payload["progress_path"] = str(progress)
        print(json.dumps(payload, indent=2))
        return 0 if report.months_with_data > 0 else 1

    report = run_gate_benchmark(
        start=start,
        end=end,
        use_snapshots=use_snapshots,
        write_snapshots=write_snapshots,
        include_slippage=not getattr(args, "no_slippage", False),
        snapshot_config_hash=snap_hash,
    )
    print(json.dumps(report.to_dict(), indent=2))
    return 0 if report.runners > 0 else 1


def cmd_snapshot_backfill(args: argparse.Namespace) -> int:
    from hibs_racing.backtest.gate_benchmark import backfill_scored_snapshots

    result = backfill_scored_snapshots(
        start=args.start,
        end=args.end,
        force=getattr(args, "force", False),
    )
    print(json.dumps(result, indent=2))
    if result.get("rows_written", 0) > 0:
        return 0
    if result.get("complete"):
        return 0
    return 1


def cmd_gate2_sensitivity(args: argparse.Namespace) -> int:
    from hibs_racing.backtest.gate2_sensitivity import run_gate2_cap_sensitivity

    report = run_gate2_cap_sensitivity(
        start=getattr(args, "start", None),
        end=getattr(args, "end", None),
        days=int(getattr(args, "days", 90)),
        use_snapshots=not getattr(args, "no_snapshots", False),
    )
    print(json.dumps(report.to_dict(), indent=2))
    return 0 if report.with_caps.get("gate2", {}).get("picks", 0) else 1


def cmd_gate_regression(args: argparse.Namespace) -> int:
    from hibs_racing.backtest.gate_regression import run_gate_regression_check

    check = run_gate_regression_check(
        days=int(getattr(args, "days", 90)),
        start=getattr(args, "start", None),
        end=getattr(args, "end", None),
        require_snapshots=getattr(args, "require_snapshots", False),
    )
    print(json.dumps(check.to_dict(), indent=2))
    return 0 if check.passed else 1


def cmd_gate_coverage_audit(args: argparse.Namespace) -> int:
    from hibs_racing.analytics.gate_audit import run_gate_coverage_audit

    lanes_raw = getattr(args, "lanes", None)
    lanes = tuple(s.strip() for s in lanes_raw.split(",") if s.strip()) if lanes_raw else None
    report = run_gate_coverage_audit(
        start=getattr(args, "start", None),
        end=getattr(args, "end", None),
        snapshot_config_hash=getattr(args, "snapshot_config_hash", None),
        lanes=lanes,
        min_density_pct=getattr(args, "min_density", None),
        source=getattr(args, "source", "both"),
        coverage_universe=getattr(args, "coverage_universe", "domestic_gb_ire"),
    )
    print(json.dumps(report, indent=2))
    if report.get("error"):
        return 1
    return 0 if report.get("retest_ready") else 1


def cmd_repair_dense_fields(args: argparse.Namespace) -> int:
    from hibs_racing.ingest.dense_field_repair import run_dense_field_repair

    report = run_dense_field_repair(
        start=getattr(args, "start"),
        end=getattr(args, "end"),
        fetch_missing=getattr(args, "fetch_missing", False),
        refill=getattr(args, "refill", False),
        max_days=getattr(args, "max_days", None),
    )
    print(json.dumps(report, indent=2))
    return 0


def cmd_gate_impact(args: argparse.Namespace) -> int:
    from hibs_racing.config import ROOT
    from hibs_racing.backtest.gate_impact import run_gate_impact, run_gate_lane_walkforward

    start = getattr(args, "start", None)
    end = getattr(args, "end", None)
    snap_hash = getattr(args, "snapshot_config_hash", None)
    if getattr(args, "walkforward", False):
        out = getattr(args, "output", None) or (ROOT / "exports" / "gate_lane_walkforward.json")
        progress = out.with_name("gate_lane_walkforward_progress.json")
        report = run_gate_lane_walkforward(
            start=start,
            end=end,
            snapshot_config_hash=snap_hash,
            progress_path=progress,
        )
        payload = dict(report)
        if not report.get("error"):
            Path(out).parent.mkdir(parents=True, exist_ok=True)
            Path(out).write_text(json.dumps(payload, indent=2), encoding="utf-8")
            payload["output_path"] = str(out)
            payload["progress_path"] = str(progress)
        print(json.dumps(payload, indent=2))
        if report.get("error"):
            return 1
        return 0 if report.get("months_with_data", 0) > 0 else 1

    report = run_gate_impact(
        start=start,
        end=end,
        snapshot_config_hash=snap_hash,
        baseline_col=getattr(args, "baseline_lane", "flag_gate2"),
    )
    print(json.dumps(report, indent=2))
    if report.get("error"):
        return 1
    return 0 if report.get("runners", 0) > 0 else 1


def cmd_data_integrity_check(args: argparse.Namespace) -> int:
    from hibs_racing.cards.ui_frame import prune_orphan_card_scores
    from hibs_racing.monitoring.nan_alert import run_nan_integrity_check

    if getattr(args, "repair", False):
        from hibs_racing.cards.ui_frame import repair_value_gate_reasons

        pruned = prune_orphan_card_scores()
        repaired = repair_value_gate_reasons()
        print(
            json.dumps(
                {"orphan_card_scores_pruned": pruned, "value_gate_reasons_nulled": repaired},
                indent=2,
            )
        )
    report = run_nan_integrity_check(strict=bool(getattr(args, "strict", True)))
    print(json.dumps(report.to_dict(), indent=2))
    return 0 if report.passed else 1


def cmd_institutional_check(args: argparse.Namespace) -> int:
    from hibs_racing.institutional.check import run_institutional_check

    report = run_institutional_check(
        days=int(getattr(args, "days", 90)),
        card_date=getattr(args, "card_date", None),
        require_snapshots=getattr(args, "require_snapshots", True),
        require_recon_clean=getattr(args, "require_recon_clean", False),
        observation_lane=bool(getattr(args, "observation_lane", False)),
        min_card_days=getattr(args, "min_card_days", None),
    )
    print(json.dumps(report.to_dict(), indent=2))
    return 0 if report.passed else 1


def cmd_retain_logs(args: argparse.Namespace) -> int:
    from hibs_racing.institutional.log_retention import run_log_retention

    report = run_log_retention(
        detailed_days=getattr(args, "detailed_days", None),
        brief_days=getattr(args, "brief_days", None),
        dry_run=bool(getattr(args, "dry_run", False)),
        files=not getattr(args, "skip_files", False),
        database_audit=not getattr(args, "skip_db", False),
    )
    print(json.dumps(report.to_dict(), indent=2))
    return 0


def cmd_reconcile_paper(args: argparse.Namespace) -> int:
    import pandas as pd
    from hibs_racing.config import db_path, load_config
    from hibs_racing.features.store import connect, init_db
    from hibs_racing.institutional.paper_reconciliation import (
        reconcile_paper_ledger,
        sync_paper_ledger_to_scored,
    )
    from hibs_racing.cards.score_card import score_upcoming_cards

    card_date = args.card_date
    if getattr(args, "sync", False):
        db = db_path(load_config())
        init_db(db)
        with connect(db) as conn:
            cards = pd.read_sql_query(
                "SELECT * FROM upcoming_runners WHERE card_date = ?",
                conn,
                params=(card_date,),
            )
        if cards.empty:
            print(json.dumps({"ok": False, "error": f"No upcoming_runners for {card_date}"}))
            return 1
        odds = cards[["runner_id", "win_decimal", "place_fraction", "places"]]
        scored = score_upcoming_cards(cards, database=db, odds=odds, persist=True, write_snapshot=False)
        result = sync_paper_ledger_to_scored(scored, card_date=card_date, database=db)
    else:
        result = reconcile_paper_ledger(card_date)
    print(json.dumps(result.to_dict(), indent=2))
    return 0 if result.is_clean else 1


def cmd_backtest_replay(args: argparse.Namespace) -> int:
    from hibs_racing.backtest.retrospective import export_oos_ledger

    start = getattr(args, "start", None)
    end = getattr(args, "end", None)
    report = run_retrospective_backtest(
        months=int(getattr(args, "months", 3)),
        start=start,
        end=end,
        replace=not getattr(args, "keep", False),
    )
    payload = report.to_dict()
    if getattr(args, "export_ledger", False) and start and end:
        out = export_oos_ledger(
            start=start,
            end=end,
            output_path=getattr(args, "export_path", None),
        )
        payload["export_path"] = str(out)
        payload["export_rows"] = max(0, out.read_text(encoding="utf-8").count("\n") - 1)
    print(json.dumps(payload, indent=2))
    return 0 if report.value_picks_logged or report.runners_scored else 1


def cmd_export_backtest_master(args: argparse.Namespace) -> int:
    from hibs_racing.backtest.retrospective import write_master_ledger

    start = getattr(args, "start", None) or "2025-12-01"
    end = getattr(args, "end", None) or "2026-05-31"
    out, summary = write_master_ledger(
        start=start,
        end=end,
        output_path=getattr(args, "export_path", None),
    )
    print(json.dumps({**summary, "ok": True}, indent=2))
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
        comments_only=True if args.pipeline else None,
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


def cmd_train_ranker(args: argparse.Namespace) -> int:
    # Institutional++ Invariant Feature Matrix Alignment Layer
    # Prevents matrix collapse across sparse enrichment features
    import lightgbm as lgb
    import pandas as pd
    import numpy as np

    manifest_48 = [
        "official_rating", "rpr", "combo_bayes_win", "combo_bayes_place", "combo_prior_rides",
        "jockey_bayes_place", "trainer_bayes_place", "jockey_place_90d", "trainer_place_90d",
        "jockey_place_14d", "trainer_place_14d", "jockey_consistency", "trainer_consistency",
        "jockey_vs_field", "trainer_vs_field", "jockey_cd_bayes_place", "trainer_cd_bayes_place",
        "combo_cd_bayes_place", "combo_cd_prior_rides", "jockey_cdd_bayes_place", "trainer_cdd_bayes_place",
        "combo_cdd_bayes_place", "jockey_cd_vs_field", "trainer_cd_vs_field", "combo_cd_vs_field",
        "combo_cdd_vs_field", "hidden_potential", "or_vs_field", "rpr_vs_field", "nlp_pace_vs_field",
        "nlp_pace_rank", "combo_vs_field", "draw_bias_z", "sectional_composite", "finishing_burst_level",
        "days_since_last_run", "horse_course_win_rate", "horse_distance_win_rate", "horse_going_win_rate",
        "jockey_rp_14d_win_rate", "trainer_rp_14d_win_rate", "trainer_rtf", "trainer_14d_strike",
        "form_lto_position", "form_trip_change_f", "form_cd_flag", "form_bf_flag", "form_poor_runs_3"
    ]

    # Intercept LightGBM predict and train structures globally in this runtime context
    orig_predict = lgb.Booster.predict
    def safe_predict(self, data, *args, **kwargs):
        if isinstance(data, pd.DataFrame):
            for col in manifest_48:
                if col not in data.columns:
                    data[col] = np.nan
            # Re-align ordering cleanly to fit the trained model array dimensions
            base_cols = [c for c in data.columns if c not in manifest_48]
            data = data[base_cols + manifest_48]
        return orig_predict(self, data, *args, **kwargs)
    lgb.Booster.predict = safe_predict

    from hibs_racing.models.lgbm_ranker import train_lgbm_ranker

    try:
        report = train_lgbm_ranker(
            with_enrich=bool(getattr(args, "with_enrich", False)),
            save_stable_hash=bool(getattr(args, "save_stable_hash", False)),
        )
    except ImportError as exc:
        print(json.dumps({"message": str(exc)}, indent=2))
        return 1
    print(json.dumps(report.to_dict(), indent=2))
    return 0 if report.model_path or not getattr(args, "save_stable_hash", False) else 1


def cmd_backfill_runner_enrich(args: argparse.Namespace) -> int:
    from hibs_racing.features.runner_enrich_backfill import backfill_runner_enrich

    result = backfill_runner_enrich(
        racecards_dir=getattr(args, "racecards_dir", None),
        include_upcoming=not getattr(args, "skip_upcoming", False),
        card_date=getattr(args, "card_date", None),
    )
    print(json.dumps(result, indent=2))
    return 0


def cmd_backfill_derived_enrich(args: argparse.Namespace) -> int:
    from hibs_racing.ingest.enrich_backup import derive_enrich_for_date

    result = derive_enrich_for_date(
        args.card_date,
        only_missing=not getattr(args, "refill", False),
    )
    print(json.dumps(result, indent=2))
    return 0


def cmd_batch_enrich_recovery(args: argparse.Namespace) -> int:
    import logging

    from hibs_racing.ingest.batch_enrich_recovery import run_batch_enrich_recovery

    if getattr(args, "verbose", False):
        logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    report = run_batch_enrich_recovery(
        start=getattr(args, "start", None),
        end=getattr(args, "end", None),
        resume=not getattr(args, "no_resume", False),
        max_days=getattr(args, "max_days", None),
        skip_existing_json=not getattr(args, "refetch", False),
    )
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

    milestone = getattr(args, "milestone", None) or "pre_race_30m"
    if args.once:
        report = poll_matchbook_odds_once(poll_milestone=milestone)
        print(json.dumps({**report.to_dict(), "poll_milestone": milestone}, indent=2))
        return 0 if not report.errors or report.runners_priced > 0 else 1
    run_matchbook_poll_loop(interval_seconds=args.interval, max_cycles=args.max_cycles)
    return 0


def cmd_dry_run_quotes(_: argparse.Namespace) -> int:
    from hibs_racing.odds.exchange_quotes import dry_run_exchange_quotes

    result = dry_run_exchange_quotes()
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


def cmd_join_execution_slippage(args: argparse.Namespace) -> int:
    from hibs_racing.odds.exchange_quotes import join_sp_to_value_picks

    dates = None
    if getattr(args, "card_dates", None):
        dates = [d.strip() for d in args.card_dates.split(",") if d.strip()]
    result = join_sp_to_value_picks(card_dates=dates, days=getattr(args, "days", None))
    print(json.dumps(result, indent=2))
    return 0


def cmd_weekly_gate_efficacy(args: argparse.Namespace) -> int:
    from datetime import date as date_cls

    from hibs_racing.institutional.weekly_gate_efficacy import append_weekly_report, build_weekly_report

    ended = getattr(args, "week_ended", None)
    week_ended = date_cls.fromisoformat(ended) if ended else date_cls.today()
    if not getattr(args, "no_append", False):
        payload = append_weekly_report(week_ended=week_ended)
    else:
        payload = build_weekly_report(week_ended=week_ended)
    print(json.dumps(payload, indent=2, default=str))
    return 0 if payload.get("ok") else 1


def cmd_win_prob_calibration_fit(args: argparse.Namespace) -> int:
    from hibs_racing.models.win_prob_calibration import fit_from_settled_paper

    days = int(getattr(args, "days", 365) or 365)
    payload = fit_from_settled_paper(days=days)
    print(json.dumps(payload, indent=2, default=str))
    if not payload.get("knots"):
        print("WARN: insufficient settled paper rows for isotonic fit", file=sys.stderr)
        return 1
    return 0


def cmd_route_execution(args: argparse.Namespace) -> int:
    from hibs_racing.live.execution_config import EXECUTION_DISABLED_MSG
    from hibs_racing.live.execution_router import route_execution_batch

    report = route_execution_batch([], log_results=False)
    print(json.dumps({**report, "cli_note": EXECUTION_DISABLED_MSG}, indent=2))
    return 0 if report.get("status") == "disabled" else 1


def cmd_trading_daemon(args: argparse.Namespace) -> int:
    import asyncio

    from hibs_racing.trading.daemon import TradingDaemon

    daemon = TradingDaemon()

    async def _main() -> None:
        await daemon.start()
        try:
            while True:
                await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            pass
        finally:
            await daemon.stop()

    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        print(json.dumps({"ok": True, "stopped": True, **daemon.status()}, indent=2))
    return 0


def cmd_trading_dispatch(args: argparse.Namespace) -> int:
    from hibs_racing.trading.daemon import TradingDaemon
    from hibs_racing.trading.execution_governor import build_order_payload

    daemon = TradingDaemon()
    if args.inject_odds:
        parts = str(args.inject_odds).split(":")
        if len(parts) == 3:
            daemon.listener.inject_delta(
                {
                    "market_id": parts[0],
                    "runner_id": parts[1],
                    "back_odds": float(parts[2]),
                    "ts_ms": int(__import__("time").time() * 1000),
                }
            )
    payload = build_order_payload(
        market_id=args.market_id,
        runner_id=args.runner_id,
        odds=float(args.odds),
        stake=float(args.stake),
    )
    if args.latency_ms is not None:
        payload["created_at_ms"] = int(__import__("time").time() * 1000) - int(args.latency_ms)
    result = daemon.submit_order(payload)
    print(json.dumps(result, indent=2))
    return 0 if result.get("allowed") else 1


def cmd_trading_status(args: argparse.Namespace) -> int:
    from hibs_racing.trading.daemon import TradingDaemon
    from hibs_racing.trading.store import recent_simulated_trades

    daemon = TradingDaemon()
    print(
        json.dumps(
            {
                **daemon.status(),
                "recent_simulated_trades": recent_simulated_trades(limit=int(args.limit)),
            },
            indent=2,
            default=str,
        )
    )
    return 0


def cmd_notify_daily(args: argparse.Namespace) -> int:
    from hibs_racing.daily.webhook_notify import notify_daily_digest

    report = notify_daily_digest(limit=int(getattr(args, "top", 3)))
    print(json.dumps(report, indent=2))
    if report.get("skipped"):
        return 0
    return 0 if report.get("ok") else 1


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
            poll_milestone=getattr(args, "poll_milestone", None),
        )
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, **stats}, indent=2))
    try:
        from hibs_racing.models.win_engine_circuit import run_win_engine_sandbox

        stats["win_engine"] = run_win_engine_sandbox()
    except Exception:
        stats["win_engine"] = {"ok": False, "skipped": True}
    if args.paper and not stats.get("paper_recon_clean", True):
        return 1
    return 0


def cmd_fetch_cards(args: argparse.Namespace) -> int:
    from hibs_racing.cards.store import store_upcoming_runners
    from hibs_racing.ingest.racecards import load_racecard_frames, parse_racecard_json
    from hibs_racing.ingest.racing_api import fetch_racing_api_racecards
    from hibs_racing.scrapers.racing_scrape_api import resolve_cards_source

    source = resolve_cards_source(args.source)
    try:
        if source == "racing_api":
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
        card_date = str(cards["card_date"].iloc[0]) if "card_date" in cards.columns else None
        if card_date:
            from hibs_racing.institutional.paper_reconciliation import sync_paper_ledger_to_scored

            recon = sync_paper_ledger_to_scored(
                scored,
                card_date=card_date,
                stake=float(load_config().get("paper", {}).get("default_stake", 1.0)),
            )
            ids = list(range(recon.expected_value_picks))
        else:
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
    from hibs_racing.odds.exchange_quotes import join_sp_to_value_picks
    from hibs_racing.place.paper_ledger import settle_paper_bets

    result = settle_paper_bets()
    slippage = join_sp_to_value_picks(days=14)
    result["execution_slippage_join"] = slippage
    try:
        from hibs_racing.models.win_engine_circuit import run_win_engine_sandbox

        result["win_engine_calibration"] = run_win_engine_sandbox()
    except Exception:
        result["win_engine_calibration"] = {"ok": False, "skipped": True}
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
    _load_dotenv_if_present()
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

    p_cg = sub.add_parser(
        "compare-gates",
        help="Compare raw value flags vs gated value flags on recent stored cards",
    )
    p_cg.add_argument("--days", type=int, default=14, help="How many latest card dates to include")
    p_cg.set_defaults(func=cmd_compare_gates)

    p_bg = sub.add_parser(
        "benchmark-gates",
        help="Historical benchmark: none vs gate1 vs gate1+gate2 on settled SP data",
    )
    p_bg.add_argument("--start", help="Start date YYYY-MM-DD (default: earliest available)")
    p_bg.add_argument("--end", help="End date YYYY-MM-DD (default: latest available)")
    p_bg.add_argument(
        "--walkforward",
        action="store_true",
        help="Month-by-month benchmark with aggregate + per-period rows",
    )
    p_bg.add_argument(
        "--output",
        type=Path,
        help="Write walk-forward JSON report (default: exports/gate_walkforward.json)",
    )
    p_bg.add_argument(
        "--no-snapshots",
        action="store_true",
        help="Force full re-score (ignore scored_runner_snapshots)",
    )
    p_bg.add_argument(
        "--write-snapshots",
        action="store_true",
        help="Persist snapshots while benchmarking (slow; use snapshot-backfill instead)",
    )
    p_bg.add_argument(
        "--no-slippage",
        action="store_true",
        help="Skip slippage stress lanes in single-window benchmark",
    )
    p_bg.add_argument(
        "--snapshot-config-hash",
        metavar="HASH",
        help="Snapshot config_hash to replay (prefix OK). Use 'best' for largest backfill in DB.",
    )
    p_bg.set_defaults(func=cmd_benchmark_gates)

    p_snap = sub.add_parser(
        "snapshot-backfill",
        help="Build scored_runner_snapshots for historical SP replay",
    )
    p_snap.add_argument("--start", required=True, help="Start date YYYY-MM-DD")
    p_snap.add_argument("--end", required=True, help="End date YYYY-MM-DD")
    p_snap.add_argument("--force", action="store_true", help="Rebuild even if coverage complete")
    p_snap.set_defaults(func=cmd_snapshot_backfill)

    p_g2s = sub.add_parser(
        "gate2-sensitivity",
        help="Compare Gate2 with portfolio caps ON vs OFF",
    )
    p_g2s.add_argument("--start", help="Start date YYYY-MM-DD")
    p_g2s.add_argument("--end", help="End date YYYY-MM-DD")
    p_g2s.add_argument("--days", type=int, default=90, help="Lookback when start/end omitted")
    p_g2s.add_argument("--no-snapshots", action="store_true")
    p_g2s.set_defaults(func=cmd_gate2_sensitivity)

    p_gr = sub.add_parser(
        "gate-regression",
        help="CI gate check: Gate1 must not regress vs raw value flags",
    )
    p_gr.add_argument("--days", type=int, default=90)
    p_gr.add_argument("--start", help="Start date YYYY-MM-DD")
    p_gr.add_argument("--end", help="End date YYYY-MM-DD")
    p_gr.add_argument(
        "--require-snapshots",
        action="store_true",
        help="Fail if snapshot coverage incomplete for window",
    )
    p_gr.set_defaults(func=cmd_gate_regression)

    p_gi = sub.add_parser(
        "gate-impact",
        help="Marginal ROI per block reason + Gate3/Gate4 experimental lanes (snapshot replay)",
    )
    p_gi.add_argument("--start", help="Start date YYYY-MM-DD")
    p_gi.add_argument("--end", help="End date YYYY-MM-DD")
    p_gi.add_argument(
        "--snapshot-config-hash",
        metavar="HASH",
        help="Snapshot config_hash (prefix OK). Use 'best' for largest backfill.",
    )
    p_gi.add_argument(
        "--baseline-lane",
        default="flag_gate2",
        choices=["flag_gate2", "flag_gate1", "flag_production"],
        help="Lane whose block reasons to stress-test (default: flag_gate2)",
    )
    p_gi.add_argument(
        "--walkforward",
        action="store_true",
        help="Month-by-month Gate2 vs Gate3 vs Gate4 comparison",
    )
    p_gi.add_argument(
        "--output",
        type=Path,
        help="Write walk-forward JSON (default: exports/gate_lane_walkforward.json)",
    )
    p_gi.set_defaults(func=cmd_gate_impact)

    p_gca = sub.add_parser(
        "gate-coverage-audit",
        help="Audit snapshot replay window for gate data deprivation before archiving lanes",
    )
    p_gca.add_argument("--start", help="Start date YYYY-MM-DD")
    p_gca.add_argument("--end", help="End date YYYY-MM-DD")
    p_gca.add_argument(
        "--snapshot-config-hash",
        metavar="HASH",
        help="Snapshot config_hash (prefix OK). Use 'best' for largest backfill.",
    )
    p_gca.add_argument(
        "--lanes",
        help="Comma-separated lanes (default: gate2,gate3,gate5,gate6,gate7,gate8)",
    )
    p_gca.add_argument(
        "--min-density",
        type=float,
        help="Override min_gate_data_density_pct (default from config)",
    )
    p_gca.add_argument(
        "--source",
        choices=["both", "snapshots", "runners"],
        default="both",
        help="Audit snapshots (replay), runners DB (batch inject), or both",
    )
    p_gca.add_argument(
        "--coverage-universe",
        choices=["domestic_gb_ire", "all", "international"],
        default="domestic_gb_ire",
        help="Runner universe for retest_ready (default: UK/IRE domestic replay)",
    )
    p_gca.set_defaults(func=cmd_gate_coverage_audit)

    p_dic = sub.add_parser(
        "data-integrity-check",
        help="Strict NaN + DB/UI sync audit (local Mac — no email)",
    )
    p_dic.add_argument("--strict", action="store_true", default=True)
    p_dic.add_argument("--no-strict", action="store_false", dest="strict")
    p_dic.add_argument("--repair", action="store_true", help="Prune orphan card_scores before check")
    p_dic.set_defaults(func=cmd_data_integrity_check)

    p_ic = sub.add_parser(
        "institutional-check",
        help="Phase 3: snapshots + gate regression + optional paper recon",
    )
    p_ic.add_argument("--days", type=int, default=90)
    p_ic.add_argument("--card-date", help="Optional card date for paper recon")
    p_ic.add_argument("--require-snapshots", action="store_true", default=True)
    p_ic.add_argument("--no-require-snapshots", action="store_false", dest="require_snapshots")
    p_ic.add_argument("--require-recon-clean", action="store_true")
    p_ic.add_argument(
        "--observation-lane",
        action="store_true",
        help="Pre-WC lane: require today's snapshot + clean paper recon; skip 7d gate regression",
    )
    p_ic.add_argument(
        "--min-card-days",
        type=int,
        default=None,
        help="Override paper.regression.min_card_days for gate regression",
    )
    p_ic.set_defaults(func=cmd_institutional_check)

    p_rp = sub.add_parser("reconcile-paper", help="Reconcile paper_bets vs production value picks")
    p_rp.add_argument("--card-date", required=True, help="Card date YYYY-MM-DD")
    p_rp.add_argument(
        "--sync",
        action="store_true",
        help="Prune stale ledger rows and align to current scored value flags",
    )
    p_rp.set_defaults(func=cmd_reconcile_paper)

    p_lr = sub.add_parser(
        "retain-logs",
        help="Tiered log retention: 30d detailed, 120d brief (audit logs only)",
    )
    p_lr.add_argument("--detailed-days", type=int, help="Full-detail window (default: config)")
    p_lr.add_argument("--brief-days", type=int, help="Brief archive window (default: config)")
    p_lr.add_argument("--dry-run", action="store_true", help="Report only; do not prune")
    p_lr.add_argument("--skip-files", action="store_true", help="Skip cron log files")
    p_lr.add_argument("--skip-db", action="store_true", help="Skip ledger_events + run_manifests")
    p_lr.set_defaults(func=cmd_retain_logs)

    p_btr = sub.add_parser(
        "backtest-replay",
        help="Replay last N months of GB/IRE cards — log value picks vs outcomes (SP odds)",
    )
    p_btr.add_argument("--months", type=int, default=3, help="Lookback months (default 3)")
    p_btr.add_argument("--start", help="Start date YYYY-MM-DD (overrides --months)")
    p_btr.add_argument("--end", help="End date YYYY-MM-DD (default today)")
    p_btr.add_argument("--keep", action="store_true", help="Keep existing backtest ledger rows")
    p_btr.add_argument(
        "--export-ledger",
        action="store_true",
        help="Write sanitized OOS CSV to exports/ (requires --start and --end)",
    )
    p_btr.add_argument(
        "--export-path",
        type=Path,
        help="Custom CSV output path (default: exports/Hibs_Racing_OOS_PhaseA_May2026_TrackRecord.csv)",
    )
    p_btr.set_defaults(func=cmd_backtest_replay)

    p_btm = sub.add_parser(
        "export-backtest-master",
        help="Export aggregated backtest CSV with calibration vs OOS labels",
    )
    p_btm.add_argument("--start", default="2025-12-01", help="Start date YYYY-MM-DD")
    p_btm.add_argument("--end", default="2026-05-31", help="End date YYYY-MM-DD")
    p_btm.add_argument("--export-path", type=Path, help="Output CSV path")
    p_btm.set_defaults(func=cmd_export_backtest_master)

    p_matrix = sub.add_parser("build-matrix", help="Build LTR feature matrix (combo + NLP + relative)")
    p_matrix.set_defaults(func=cmd_build_matrix)

    p_ranker = sub.add_parser("train-ranker", help="Train LightGBM LambdaRank (needs .[ranker] extra)")
    p_ranker.add_argument(
        "--with-enrich",
        action="store_true",
        help="Train with RP enrich features (48 cols); saves lgbm_ranker_features_enrich.json",
    )
    p_ranker.add_argument(
        "--save-stable-hash",
        action="store_true",
        help="Pin ranker_manifest.json with content hash; enforce min_holdout_top1_enrich",
    )
    p_ranker.set_defaults(func=cmd_train_ranker)

    p_enrich_bf = sub.add_parser(
        "backfill-runner-enrich",
        help="Backfill historical runners enrich columns from upcoming_runners + RP racecard JSON",
    )
    p_enrich_bf.add_argument(
        "--racecards-dir",
        type=Path,
        help="Override rpscrape racecards directory (default: vendor/rpscrape/racecards)",
    )
    p_enrich_bf.add_argument(
        "--skip-upcoming",
        action="store_true",
        help="Only backfill from cached RP racecard JSON",
    )
    p_enrich_bf.add_argument("--card-date", help="Backfill only this YYYY-MM-DD racecard")
    p_enrich_bf.set_defaults(func=cmd_backfill_runner_enrich)

    p_derived = sub.add_parser(
        "backfill-derived-enrich",
        help="Offline enrich from raceform history (backup when RP scrape unavailable)",
    )
    p_derived.add_argument("--card-date", required=True, help="YYYY-MM-DD card to derive")
    p_derived.add_argument(
        "--refill",
        action="store_true",
        help="Overwrite rows even if enrich_source is already set",
    )
    p_derived.set_defaults(func=cmd_backfill_derived_enrich)

    p_batch = sub.add_parser(
        "batch-enrich-recovery",
        help="Scrape historical RP racecards + backfill runner enrich (checkpoint resume)",
    )
    p_batch.add_argument("--start", help="Start YYYY-MM-DD (default: batch_enrich_recovery.start)")
    p_batch.add_argument("--end", help="End YYYY-MM-DD (default: batch_enrich_recovery.end)")
    p_batch.add_argument("--max-days", type=int, help="Pilot: process at most N days")
    p_batch.add_argument("--no-resume", action="store_true", help="Ignore checkpoint")
    p_batch.add_argument("--refetch", action="store_true", help="Re-fetch JSON even if cached")
    p_batch.add_argument("-v", "--verbose", action="store_true", help="INFO logging to stderr")
    p_batch.set_defaults(func=cmd_batch_enrich_recovery)

    p_dense = sub.add_parser(
        "repair-dense-fields",
        help="Repair historical official_rating/trainer_rtf from cached or fetched RP racecards",
    )
    p_dense.add_argument("--start", required=True, help="Start YYYY-MM-DD")
    p_dense.add_argument("--end", required=True, help="End YYYY-MM-DD")
    p_dense.add_argument(
        "--fetch-missing",
        action="store_true",
        help="Fetch RP racecard JSON for missing dates before repair",
    )
    p_dense.add_argument(
        "--refill",
        action="store_true",
        help="Overwrite existing official_rating/trainer_rtf values from RP payloads",
    )
    p_dense.add_argument("--max-days", type=int, help="Pilot: process at most N days")
    p_dense.set_defaults(func=cmd_repair_dense_fields)

    p_fi = sub.add_parser("feature-importance", help="Feature importance matrix + holdout AUC diagnostic")
    p_fi.add_argument("--json", action="store_true", help="Output JSON")
    p_fi.set_defaults(func=cmd_feature_importance)

    p_poll = sub.add_parser("poll-odds", help="Matchbook steam/drift polling loop (default 120s)")
    p_poll.add_argument("--once", action="store_true", help="Single poll cycle")
    p_poll.add_argument("--interval", type=int, default=120, help="Seconds between polls")
    p_poll.add_argument("--max-cycles", type=int, help="Stop after N cycles (default: infinite)")
    p_poll.add_argument(
        "--milestone",
        default="pre_race_30m",
        help="Poll label stored in exchange_quotes (e.g. pre_race_30m, baseline)",
    )
    p_poll.set_defaults(func=cmd_poll_odds)

    p_drq = sub.add_parser(
        "dry-run-quotes",
        help="Fetch Matchbook quotes for upcoming cards and persist to exchange_quotes (no score)",
    )
    p_drq.set_defaults(func=cmd_dry_run_quotes)

    p_join = sub.add_parser(
        "join-execution-slippage",
        help="Join official SP to value_pick_execution after results ingest",
    )
    p_join.add_argument("--days", type=int, default=14, help="Lookback days when --card-dates omitted")
    p_join.add_argument("--card-dates", help="Comma-separated card dates (YYYY-MM-DD)")
    p_join.set_defaults(func=cmd_join_execution_slippage)

    p_wge = sub.add_parser(
        "weekly-gate-efficacy",
        help="Build weekly gate lane table (SP vs executed ROI) and append reports/weekly_gate_efficacy.md",
    )
    p_wge.add_argument("--week-ended", help="ISO week end date (default: today)")
    p_wge.add_argument("--no-append", action="store_true", help="Print JSON only; do not append markdown")
    p_wge.set_defaults(func=cmd_weekly_gate_efficacy)

    p_wpc = sub.add_parser(
        "win-prob-calibration-fit",
        help="Fit isotonic win-prob calibration from settled forward paper bets",
    )
    p_wpc.add_argument("--days", type=int, default=365, help="Lookback days for fit sample")
    p_wpc.set_defaults(func=cmd_win_prob_calibration_fit)

    p_fc = sub.add_parser("fetch-cards", help="Fetch upcoming racecards (rpscrape or Racing API)")
    p_fc.add_argument("--day", type=int, default=1, help="Single day: 1=today, 2=tomorrow")
    p_fc.add_argument(
        "--days",
        type=int,
        help="Range: 1=today only, 2=today+tomorrow (rpscrape --days N)",
    )
    p_fc.add_argument("--region", default="gb")
    p_fc.add_argument("--source", choices=["auto", "rpscrape", "racing_api"], default="rpscrape")
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
    p_refresh.add_argument("--source", choices=["auto", "rpscrape", "racing_api"], default="auto")
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
    p_refresh.add_argument(
        "--poll-milestone",
        help="exchange_quotes label (default: baseline via HIBS_POLL_MILESTONE or baseline)",
    )
    p_refresh.set_defaults(func=cmd_refresh_cards)

    p_exec = sub.add_parser(
        "route-execution",
        help="(Disabled) Legacy execution preview — analytics-only product",
    )
    p_exec.set_defaults(func=cmd_route_execution)

    p_td = sub.add_parser(
        "trading-daemon",
        help="Background async stream listener + execution governor (isolated; feature-flagged)",
    )
    p_td.set_defaults(func=cmd_trading_daemon)

    p_tdispatch = sub.add_parser(
        "trading-dispatch",
        help="Submit one order through execution governor (simulated when live flag false)",
    )
    p_tdispatch.add_argument("--market-id", required=True)
    p_tdispatch.add_argument("--runner-id", required=True)
    p_tdispatch.add_argument("--odds", required=True, type=float)
    p_tdispatch.add_argument("--stake", required=True, type=float)
    p_tdispatch.add_argument(
        "--inject-odds",
        help="Optional market:runner:odds injected into stream cache before dispatch",
    )
    p_tdispatch.add_argument(
        "--latency-ms",
        type=int,
        help="Synthetic packet delay for latency gate testing",
    )
    p_tdispatch.set_defaults(func=cmd_trading_dispatch)

    p_tstatus = sub.add_parser("trading-status", help="Trading daemon / simulated_trades snapshot")
    p_tstatus.add_argument("--limit", type=int, default=10)
    p_tstatus.set_defaults(func=cmd_trading_status)

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

    p_notify = sub.add_parser(
        "notify-daily",
        help="Post top Smart Portfolio picks to Telegram/Discord (after daily refresh)",
    )
    p_notify.add_argument("--top", type=int, default=3, help="Max picks to include (default 3)")
    p_notify.set_defaults(func=cmd_notify_daily)

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
