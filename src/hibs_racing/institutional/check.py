"""Institutional++ checks — manifest, recon, regression in one pass."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from hibs_racing.backtest.gate_regression import run_gate_regression_check
from hibs_racing.backtest.snapshot_store import snapshot_coverage
from hibs_racing.config import db_path, load_config
from hibs_racing.cards.engine_profile import build_engine_profile
from hibs_racing.institutional.paper_reconciliation import reconcile_paper_ledger


@dataclass
class InstitutionalCheckReport:
    passed: bool
    checks: list[dict[str, Any]]
    gate_regression: dict[str, Any]
    snapshot_coverage: dict[str, Any]
    paper_reconciliation: dict[str, Any] | None
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "checks": self.checks,
            "gate_regression": self.gate_regression,
            "snapshot_coverage": self.snapshot_coverage,
            "paper_reconciliation": self.paper_reconciliation,
            "message": self.message,
        }


def run_institutional_check(
    *,
    days: int = 90,
    card_date: str | None = None,
    require_snapshots: bool = True,
    require_recon_clean: bool = False,
    database: Path | None = None,
) -> InstitutionalCheckReport:
    cfg = load_config()
    db = database or db_path(cfg)
    end_dt = datetime.now(timezone.utc).date()
    start_dt = end_dt - timedelta(days=days)
    start_s = start_dt.isoformat()
    end_s = end_dt.isoformat()

    checks: list[dict[str, Any]] = []
    cov = snapshot_coverage(db, start_s, end_s)
    snap_ok = cov["complete"] or not require_snapshots
    checks.append(
        {
            "name": "snapshot_coverage",
            "passed": snap_ok,
            "detail": f"{cov['snapshot_card_days']}/{cov['expected_card_days']} days ({cov['coverage_pct']}%)",
        }
    )

    gate = run_gate_regression_check(
        days=days,
        database=db,
        require_snapshots=require_snapshots,
    )
    checks.extend(gate.checks)

    profile = build_engine_profile(cfg)
    detail = (
        f"{profile.get('ranker_tier')} manifest={profile.get('ranker_feature_manifest')} "
        f"({profile.get('ranker_feature_count')} features)"
    )
    if profile.get("warning"):
        detail = f"{detail} — {profile['warning']}"
    checks.append(
        {
            "name": "ranker_profile",
            "passed": True,
            "detail": detail,
        }
    )

    recon_dict: dict[str, Any] | None = None
    if card_date:
        recon = reconcile_paper_ledger(card_date, database=db)
        recon_dict = recon.to_dict()
        recon_ok = recon.is_clean or not require_recon_clean
        checks.append(
            {
                "name": "paper_reconciliation",
                "passed": recon_ok,
                "detail": f"expected={recon.expected_value_picks} ledger={recon.ledger_value_picks}",
            }
        )

    passed = all(c["passed"] for c in checks)
    msg = "Institutional check PASSED." if passed else "Institutional check FAILED."
    return InstitutionalCheckReport(
        passed=passed,
        checks=checks,
        gate_regression=gate.to_dict(),
        snapshot_coverage=cov,
        paper_reconciliation=recon_dict,
        message=msg,
    )
