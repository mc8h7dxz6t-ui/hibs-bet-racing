"""Batch historical RP racecard scrape + runner enrich backfill with checkpoint recovery."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from hibs_racing.cards.enrich import ensure_rp_stats_settings
from hibs_racing.config import ROOT, data_dir, db_path, load_config
from hibs_racing.features.runner_enrich_backfill import backfill_runner_enrich, coverage_report
from hibs_racing.ingest.rate_limit import polite_sleep, rate_limits
from hibs_racing.ingest.enrich_backup import fetch_racecards_with_fallback
from hibs_racing.ingest.racecards import RPSCRAPE_RACECARDS

logger = logging.getLogger(__name__)

DEFAULT_START = "2025-11-01"
DEFAULT_END = "2026-05-22"


@dataclass
class BatchRecoveryReport:
    start: str
    end: str
    days_processed: int = 0
    days_fetched: int = 0
    days_skipped_existing: int = 0
    days_failed: int = 0
    rows_backfilled: int = 0
    strict_join_matches: int = 0
    loose_join_matches: int = 0
    initial_coverage_pct: float = 0.0
    final_coverage_pct: float = 0.0
    checkpoint: str | None = None
    day_log: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "start": self.start,
            "end": self.end,
            "days_processed": self.days_processed,
            "days_fetched": self.days_fetched,
            "days_skipped_existing": self.days_skipped_existing,
            "days_failed": self.days_failed,
            "rows_backfilled": self.rows_backfilled,
            "strict_join_matches": self.strict_join_matches,
            "loose_join_matches": self.loose_join_matches,
            "initial_coverage_pct": round(self.initial_coverage_pct, 2),
            "final_coverage_pct": round(self.final_coverage_pct, 2),
            "checkpoint": self.checkpoint,
            "day_log": self.day_log,
            "errors": self.errors,
            "message": (
                f"Batch recovery {self.start} → {self.end}: "
                f"coverage {self.initial_coverage_pct:.2f}% → {self.final_coverage_pct:.2f}% "
                f"({self.days_fetched} fetched, {self.rows_backfilled} runner rows updated)."
            ),
        }


def checkpoint_path(cfg: dict | None = None) -> Path:
    cfg = cfg or load_config()
    rel = cfg.get("batch_enrich_recovery", {}).get("checkpoint_file", "batch_scrape_checkpoint.txt")
    return data_dir() / rel


def load_checkpoint(cfg: dict | None = None) -> str | None:
    path = checkpoint_path(cfg)
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8").strip()
    return text or None


def save_checkpoint(card_date: str, cfg: dict | None = None) -> None:
    path = checkpoint_path(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(card_date, encoding="utf-8")


def _daterange(start: date, end: date) -> list[date]:
    days: list[date] = []
    current = start
    while current <= end:
        days.append(current)
        current += timedelta(days=1)
    return days


def _has_runners_on_date(db: Path, card_date: str) -> bool:
    from hibs_racing.features.store import connect, init_db

    init_db(db)
    with connect(db) as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM runners WHERE finish_pos IS NOT NULL AND race_date = ?",
            (card_date,),
        ).fetchone()
    return bool(row and row[0] > 0)


def run_batch_enrich_recovery(
    *,
    start: str | None = None,
    end: str | None = None,
    resume: bool = True,
    max_days: int | None = None,
    regions: tuple[str, ...] = ("gb", "ire"),
    skip_existing_json: bool = True,
    database: Path | None = None,
) -> BatchRecoveryReport:
    """
    Day-by-day historical racecard fetch + per-day backfill for the dense snapshot window.
    Uses loose join keys (date|course|horse) when off_time is missing on runners.
    """
    cfg = load_config()
    batch_cfg = cfg.get("batch_enrich_recovery", {})
    start_s = start or batch_cfg.get("start", DEFAULT_START)
    end_s = end or batch_cfg.get("end", DEFAULT_END)
    timeout_sec = int(batch_cfg.get("fetch_timeout_sec", 300))
    min_cov_target = float(batch_cfg.get("target_coverage_pct", 5.0))
    use_derived_backup = bool(batch_cfg.get("backup_derived", True))

    db = database or db_path(cfg)
    initial = coverage_report(db)
    report = BatchRecoveryReport(
        start=start_s,
        end=end_s,
        initial_coverage_pct=initial["mean_enrich_coverage_pct"],
    )

    if batch_cfg.get("fetch_stats", True):
        ensure_rp_stats_settings(fetch_stats=True)

    start_d = datetime.strptime(start_s, "%Y-%m-%d").date()
    end_d = datetime.strptime(end_s, "%Y-%m-%d").date()
    if resume:
        checkpoint = load_checkpoint(cfg)
        if checkpoint:
            try:
                resume_d = datetime.strptime(checkpoint, "%Y-%m-%d").date() + timedelta(days=1)
                if start_d <= resume_d <= end_d:
                    start_d = resume_d
                    logger.info("Resuming from checkpoint after %s", checkpoint)
            except ValueError:
                report.errors.append(f"Invalid checkpoint date: {checkpoint}")

    day_pause = float(rate_limits(cfg).get("rp_scrape_day_pause_sec", 4.0))
    region_pause = float(rate_limits(cfg).get("rp_racecard_region_pause_sec", 5.0))

    for current in _daterange(start_d, end_d):
        if max_days is not None and report.days_processed >= max_days:
            break
        if report.final_coverage_pct >= min_cov_target and report.days_processed > 0:
            logger.info("Target coverage %.2f%% reached — stopping early.", min_cov_target)
            break

        card_date = current.isoformat()
        report.days_processed += 1
        day_entry: dict[str, Any] = {"date": card_date, "fetched": False, "backfill_rows": 0}

        if not _has_runners_on_date(db, card_date):
            day_entry["skipped"] = "no_historical_runners"
            report.day_log.append(day_entry)
            save_checkpoint(card_date, cfg)
            continue

        json_path = RPSCRAPE_RACECARDS / f"{card_date}.json"
        cascade: dict[str, Any] = {}
        try:
            if skip_existing_json and json_path.exists():
                report.days_skipped_existing += 1
                day_entry["fetch"] = "cached"
                cascade = fetch_racecards_with_fallback(
                    card_date,
                    skip_cached=True,
                    use_derived_on_failure=False,
                    database=db,
                )
            else:
                cascade = fetch_racecards_with_fallback(
                    card_date,
                    skip_cached=False,
                    use_derived_on_failure=use_derived_backup,
                    database=db,
                )
            day_entry["stages"] = cascade.get("stages", [])
            day_entry["source"] = cascade.get("source")
            rows = int(cascade.get("rows_backfilled", 0))
            if cascade.get("source") == "rpscrape_racecards" or json_path.exists():
                if day_entry.get("fetch") != "cached":
                    report.days_fetched += 1
                    day_entry["fetched"] = True
            elif cascade.get("source") == "raceform_derived" and rows > 0:
                day_entry["fetched"] = False
                day_entry["backup"] = "raceform_derived"
            elif rows == 0 and not cascade.get("stages"):
                report.days_failed += 1
        except Exception as exc:
            report.days_failed += 1
            day_entry["error"] = str(exc)
            report.errors.append(f"{card_date}: {exc}")
            rows = 0

        report.rows_backfilled += rows
        day_entry["backfill_rows"] = rows
        for stage in day_entry.get("stages", []):
            if isinstance(stage, dict) and stage.get("stage") == "backfill":
                loose_n = int(stage.get("loose_join_matches", 0))
                strict_n = int(stage.get("strict_join_matches", 0))
                day_entry["loose_join_matches"] = loose_n
                day_entry["strict_join_matches"] = strict_n
                report.loose_join_matches += loose_n
                report.strict_join_matches += strict_n
        if rows > 0 or day_entry.get("fetch") == "cached" or day_entry.get("backup"):
            cov = coverage_report(db)
            day_entry["coverage_pct"] = cov["mean_enrich_coverage_pct"]
            report.final_coverage_pct = cov["mean_enrich_coverage_pct"]
            logger.info(
                "Day %s: backfill=%s rows (strict=%s loose=%s), coverage=%.2f%%",
                card_date,
                rows,
                day_entry.get("strict_join_matches", 0),
                day_entry.get("loose_join_matches", 0),
                cov["mean_enrich_coverage_pct"],
            )

        report.day_log.append(day_entry)
        report.checkpoint = card_date
        save_checkpoint(card_date, cfg)

        if day_pause > 0 and current < end_d:
            polite_sleep("rp_scrape_day_pause_sec", cfg=cfg)

    if report.final_coverage_pct == 0.0:
        report.final_coverage_pct = coverage_report(db)["mean_enrich_coverage_pct"]

    progress_path = data_dir() / batch_cfg.get("progress_file", "batch_enrich_recovery_progress.json")
    progress_path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    report.day_log = report.day_log[-30:]  # trim for CLI output
    return report
