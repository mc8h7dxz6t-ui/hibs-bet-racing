"""Institutional++ checks — manifest, recon, regression in one pass."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from hibs_racing.backtest.gate_regression import run_gate_regression_check
from hibs_racing.backtest.snapshot_store import (
    card_snapshot_present,
    scoring_config_hash,
    snapshot_card_dates,
    snapshot_coverage,
)
from hibs_racing.institutional.run_manifest import latest_manifest_for_date
from hibs_racing.config import db_path, load_config
from hibs_racing.cards.engine_profile import build_engine_profile
from hibs_racing.institutional.paper_reconciliation import reconcile_paper_ledger
from hibs_racing.institutional.telemetry_balance import telemetry_balance_for_date


@dataclass
class InstitutionalCheckReport:
    passed: bool
    checks: list[dict[str, Any]]
    gate_regression: dict[str, Any]
    snapshot_coverage: dict[str, Any]
    paper_reconciliation: dict[str, Any] | None
    telemetry_balance: dict[str, Any] | None
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "checks": self.checks,
            "gate_regression": self.gate_regression,
            "snapshot_coverage": self.snapshot_coverage,
            "paper_reconciliation": self.paper_reconciliation,
            "telemetry_balance": self.telemetry_balance,
            "message": self.message,
        }


def run_institutional_check(
    *,
    days: int = 90,
    card_date: str | None = None,
    require_snapshots: bool = True,
    require_recon_clean: bool = False,
    observation_lane: bool = False,
    min_card_days: int | None = None,
    database: Path | None = None,
) -> InstitutionalCheckReport:
    cfg = load_config()
    db = database or db_path(cfg)
    if card_date is None:
        card_date = datetime.now(timezone.utc).date().isoformat()
    end_dt = datetime.now(timezone.utc).date()
    start_dt = end_dt - timedelta(days=days)
    start_s = start_dt.isoformat()
    end_s = end_dt.isoformat()

    if observation_lane:
        require_snapshots = False
        if min_card_days is None:
            min_card_days = 1

    checks: list[dict[str, Any]] = []
    cov = snapshot_coverage(db, start_s, end_s)
    if observation_lane and card_date:
        manifest_today = latest_manifest_for_date(card_date, database=db)
        manifest_hash = manifest_today.config_hash if manifest_today else None
        live_hash = scoring_config_hash()
        today_stored = card_snapshot_present(
            db,
            card_date,
            config_hash=manifest_hash or live_hash,
        )
        hash_drift = bool(
            manifest_hash
            and manifest_hash != live_hash
            and not card_snapshot_present(db, card_date, config_hash=live_hash)
        )
        if not today_stored:
            today_stored = card_snapshot_present(db, card_date, allow_any_hash=True)
        snap_ok = today_stored
        cov = {
            **cov,
            "observation_lane": True,
            "today_card_date": card_date,
            "today_snapshot": today_stored,
            "manifest_config_hash": manifest_hash,
            "live_config_hash": live_hash,
            "config_hash_drift": hash_drift,
        }
    else:
        snap_ok = cov["complete"] or not require_snapshots
    if observation_lane and card_date:
        drift_note = " (config hash drift — refresh-cards)" if cov.get("config_hash_drift") else ""
        snap_detail = f"today {card_date} snapshot={'yes' if snap_ok else 'missing'}{drift_note}"
    else:
        snap_detail = (
            f"{cov['snapshot_card_days']}/{cov['expected_card_days']} days ({cov['coverage_pct']}%)"
        )
    checks.append(
        {
            "name": "snapshot_coverage",
            "passed": snap_ok,
            "detail": snap_detail,
        }
    )

    gate = run_gate_regression_check(
        days=days,
        database=db,
        require_snapshots=require_snapshots,
        min_card_days=min_card_days,
    )
    checks.extend(gate.checks)

    profile = build_engine_profile(cfg)
    detail = (
        f"{profile.get('ranker_tier')} manifest={profile.get('ranker_feature_manifest')} "
        f"({profile.get('ranker_feature_count')} features)"
    )
    if profile.get("warning"):
        detail = f"{detail} — {profile['warning']}"
    production_mode = os.environ.get("HIBS_RACING_PRODUCTION", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    checks.append(
        {
            "name": "ranker_profile",
            "passed": not profile.get("warning") if production_mode else True,
            "detail": detail,
        }
    )

    telemetry_dict: dict[str, Any] | None = None
    if card_date:
        telemetry = telemetry_balance_for_date(
            card_date,
            observation_lane=observation_lane,
            database=db,
        )
        telemetry_dict = telemetry.to_dict()
        checks.append(
            {
                "name": "telemetry_balance",
                "passed": telemetry.passed,
                "detail": telemetry.message,
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

    from hibs_racing.monitoring.nan_alert import run_nan_integrity_check

    nan = run_nan_integrity_check(database=db, strict=False)
    nan_detail = nan.message
    if nan.violations:
        nan_detail = f"{nan.message} — {nan.violations[0].get('code')}"
    checks.append(
        {
            "name": "nan_integrity",
            "passed": nan.passed,
            "detail": nan_detail,
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
        telemetry_balance=telemetry_dict,
        message=msg,
    )
