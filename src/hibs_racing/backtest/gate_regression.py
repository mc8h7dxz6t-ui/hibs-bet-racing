"""CI / weekly gate regression — fail when Gate1 quality filter regresses vs raw value."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from hibs_racing.backtest.gate_benchmark import run_gate_benchmark
from hibs_racing.backtest.snapshot_store import snapshot_coverage
from hibs_racing.config import db_path, load_config


@dataclass
class GateRegressionCheck:
    passed: bool
    start: str
    end: str
    checks: list[dict]
    report_summary: dict
    message: str

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "start": self.start,
            "end": self.end,
            "checks": self.checks,
            "report_summary": self.report_summary,
            "message": self.message,
        }


def _regression_cfg(paper_cfg: dict) -> dict:
    raw = paper_cfg.get("regression", {})
    return raw if isinstance(raw, dict) else {}


def run_gate_regression_check(
    *,
    days: int = 90,
    start: str | None = None,
    end: str | None = None,
    database: Path | None = None,
    require_snapshots: bool = False,
    min_card_days: int | None = None,
) -> GateRegressionCheck:
    """
  Validate Gate1 still improves on raw value over the lookback window.

  Default thresholds (override in ``paper.regression``):
  - ``min_gate1_roi_delta_pp``: Gate1 ROI must be >= none by this margin (default 0)
  - ``min_gate1_hit_rate_delta_pp``: hit rate improvement in percentage points (default 0)
  - ``min_card_days``: minimum settled card days in window (default 7)
    """
    cfg = load_config()
    paper = cfg.get("paper", {})
    reg = _regression_cfg(paper)
    db = database or db_path(cfg)

    if start is None or end is None:
        end_dt = datetime.now(timezone.utc).date()
        if end:
            end_dt = datetime.strptime(end, "%Y-%m-%d").date()
        start_dt = end_dt - timedelta(days=days)
        if start:
            start_dt = datetime.strptime(start, "%Y-%m-%d").date()
        start_s = start_dt.isoformat()
        end_s = end_dt.isoformat()
    else:
        start_s, end_s = start, end

    min_days = int(min_card_days if min_card_days is not None else reg.get("min_card_days", 7))
    min_roi_pp = float(reg.get("min_gate1_roi_delta_pp", 0.0))
    min_hit_pp = float(reg.get("min_gate1_hit_rate_delta_pp", 0.0))

    cov = snapshot_coverage(db, start_s, end_s)
    checks: list[dict] = []

    if require_snapshots and not cov["complete"]:
        checks.append(
            {
                "name": "snapshot_coverage",
                "passed": False,
                "detail": f"Snapshots incomplete ({cov['snapshot_card_days']}/{cov['expected_card_days']} days).",
            }
        )
        return GateRegressionCheck(
            passed=False,
            start=start_s,
            end=end_s,
            checks=checks,
            report_summary={},
            message="Snapshot coverage required but incomplete — run snapshot-backfill.",
        )

    report = run_gate_benchmark(
        start=start_s,
        end=end_s,
        database=db,
        use_snapshots=True,
        include_slippage=False,
    )

    if report.card_days < min_days:
        checks.append(
            {
                "name": "min_card_days",
                "passed": False,
                "detail": f"Only {report.card_days} card days (need {min_days}).",
            }
        )
        return GateRegressionCheck(
            passed=False,
            start=start_s,
            end=end_s,
            checks=checks,
            report_summary=report.to_dict(),
            message=f"Insufficient card days for regression ({report.card_days} < {min_days}).",
        )

    roi_delta = report.delta_gate1_vs_none.get("roi_change_pp")
    hit_delta = report.delta_gate1_vs_none.get("hit_rate_change_pp")

    roi_ok = roi_delta is not None and float(roi_delta) >= min_roi_pp
    hit_ok = hit_delta is not None and float(hit_delta) >= min_hit_pp

    checks.extend(
        [
            {
                "name": "gate1_roi_vs_none",
                "passed": roi_ok,
                "detail": f"ROI delta gate1-none = {roi_delta}pp (min {min_roi_pp}pp).",
            },
            {
                "name": "gate1_hit_rate_vs_none",
                "passed": hit_ok,
                "detail": f"Hit-rate delta = {hit_delta}pp (min {min_hit_pp}pp).",
            },
        ]
    )

    passed = all(c["passed"] for c in checks)
    msg = "Gate regression PASSED." if passed else "Gate regression FAILED — see checks."
    return GateRegressionCheck(
        passed=passed,
        start=start_s,
        end=end_s,
        checks=checks,
        report_summary={
            "card_days": report.card_days,
            "none": report.none,
            "gate1": report.gate1,
            "delta_gate1_vs_none": report.delta_gate1_vs_none,
            "snapshot_source": report.snapshot_source,
        },
        message=msg,
    )
