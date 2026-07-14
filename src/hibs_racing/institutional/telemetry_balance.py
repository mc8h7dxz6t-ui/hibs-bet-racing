"""Telemetry balance — institutional++ provider mix, coverage, and latency SLA."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from hibs_racing.config import load_config
from hibs_racing.institutional.contracts import RunManifest
from hibs_racing.institutional.run_manifest import latest_manifest_for_date


def _telemetry_cfg(cfg: dict | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    block = cfg.get("institutional", {}).get("telemetry_balance", {})
    return block if isinstance(block, dict) else {}


@dataclass
class TelemetryBalanceReport:
    passed: bool
    card_date: str | None
    manifest_id: str | None
    checks: list[dict[str, Any]]
    timings_ms: dict[str, float]
    shares_pct: dict[str, float]
    matchbook_coverage_ratio: float | None
    total_ms: float
    message: str
    observation_lane: bool = False
    extras: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "card_date": self.card_date,
            "manifest_id": self.manifest_id,
            "checks": self.checks,
            "timings_ms": self.timings_ms,
            "shares_pct": self.shares_pct,
            "matchbook_coverage_ratio": self.matchbook_coverage_ratio,
            "total_ms": self.total_ms,
            "message": self.message,
            "observation_lane": self.observation_lane,
            "extras": self.extras,
        }


def _stage_shares(timings: dict[str, Any]) -> tuple[dict[str, float], float]:
    numeric = {k: float(v) for k, v in timings.items() if isinstance(v, (int, float)) and v >= 0}
    total = float(numeric.get("total_ms") or sum(numeric.values()) or 0.0)
    if total <= 0:
        return {}, 0.0
    shares = {k: round(100.0 * v / total, 2) for k, v in numeric.items() if k != "total_ms"}
    return shares, total


def evaluate_telemetry_balance(
    *,
    refresh_payload: dict[str, Any] | None = None,
    manifest: RunManifest | None = None,
    observation_lane: bool = False,
    cfg: dict | None = None,
) -> TelemetryBalanceReport:
    """
    Validate balanced telemetry across Racing API (fetch), Matchbook (odds), and scoring.

    Uses refresh JSON and/or latest run manifest extras (timings_ms, exchange_audit).
    """
    cfg = cfg or load_config()
    tcfg = _telemetry_cfg(cfg)
    min_cov = float(
        tcfg.get(
            "min_matchbook_coverage_obs" if observation_lane else "min_matchbook_coverage",
            0.35 if observation_lane else 0.50,
        )
    )
    max_total_ms = float(tcfg.get("max_total_ms", 120_000.0))
    min_fetch_ms = float(tcfg.get("min_fetch_ms", 50.0))
    min_odds_ms = float(tcfg.get("min_odds_ms", 10.0))
    max_score_share = float(tcfg.get("max_score_share_pct", 92.0))
    max_odds_share = float(tcfg.get("max_odds_share_pct", 45.0))

    payload = refresh_payload or {}
    extras: dict[str, Any] = {}
    if manifest:
        extras = dict(manifest.extras or {})
        if not payload:
            payload = {
                "manifest_id": manifest.manifest_id,
                "timings_ms": extras.get("timings_ms", {}),
                "exchange_audit": extras.get("exchange_audit", {}),
                "odds_source": manifest.odds_source,
                "runners": manifest.runner_count,
            }

    timings = dict(payload.get("timings_ms") or extras.get("timings_ms") or {})
    shares, total_ms = _stage_shares(timings)
    exchange = payload.get("exchange_audit") or extras.get("exchange_audit") or {}
    cov_ratio = exchange.get("coverage_ratio")
    if cov_ratio is None and payload.get("runners") and payload.get("odds_runners"):
        try:
            cov_ratio = float(payload["odds_runners"]) / float(payload["runners"])
        except (TypeError, ValueError, ZeroDivisionError):
            cov_ratio = None

    odds_source = str(payload.get("odds_source") or (manifest.odds_source if manifest else "") or "").lower()
    card_date = payload.get("card_dates", [None])
    if isinstance(card_date, list) and card_date:
        card_date = str(card_date[0])
    elif manifest:
        card_date = manifest.card_date
    else:
        card_date = None

    checks: list[dict[str, Any]] = []

    fetch_ms = float(timings.get("fetch_ms") or 0.0)
    odds_ms = float(timings.get("odds_ms") or 0.0)
    score_ms = float(timings.get("score_ms") or 0.0)
    checks.append(
        {
            "name": "racing_api_present",
            "passed": fetch_ms >= min_fetch_ms,
            "detail": f"fetch_ms={fetch_ms:.1f} (min {min_fetch_ms})",
        }
    )
    if odds_source == "matchbook":
        checks.append(
            {
                "name": "matchbook_odds_present",
                "passed": odds_ms >= min_odds_ms,
                "detail": f"odds_ms={odds_ms:.1f} (min {min_odds_ms})",
            }
        )
    if cov_ratio is not None:
        checks.append(
            {
                "name": "matchbook_coverage",
                "passed": float(cov_ratio) >= min_cov,
                "detail": f"coverage={float(cov_ratio):.1%} (min {min_cov:.0%})",
            }
        )
    else:
        checks.append(
            {
                "name": "matchbook_coverage",
                "passed": False,
                "detail": "coverage_ratio missing — no exchange audit",
            }
        )

    score_share = shares.get("score_ms", 0.0)
    odds_share = shares.get("odds_ms", 0.0)
    checks.append(
        {
            "name": "latency_sla",
            "passed": total_ms <= max_total_ms,
            "detail": f"total_ms={total_ms:.0f} (max {max_total_ms:.0f})",
        }
    )
    checks.append(
        {
            "name": "score_share_cap",
            "passed": score_share <= max_score_share,
            "detail": f"score_ms share={score_share:.1f}% (max {max_score_share:.0f}%)",
        }
    )
    if odds_source == "matchbook" and odds_ms > 0:
        checks.append(
            {
                "name": "odds_share_cap",
                "passed": odds_share <= max_odds_share,
                "detail": f"odds_ms share={odds_share:.1f}% (max {max_odds_share:.0f}%)",
            }
        )

    errors = exchange.get("errors") or []
    checks.append(
        {
            "name": "exchange_errors",
            "passed": not errors,
            "detail": "none" if not errors else f"{len(errors)} error(s)",
        }
    )

    passed = all(c["passed"] for c in checks)
    msg = (
        "Telemetry balance PASSED."
        if passed
        else "Telemetry balance FAILED — uneven provider load or coverage."
    )
    return TelemetryBalanceReport(
        passed=passed,
        card_date=card_date,
        manifest_id=payload.get("manifest_id") or (manifest.manifest_id if manifest else None),
        checks=checks,
        timings_ms={k: float(v) for k, v in timings.items() if isinstance(v, (int, float))},
        shares_pct=shares,
        matchbook_coverage_ratio=float(cov_ratio) if cov_ratio is not None else None,
        total_ms=total_ms,
        message=msg,
        observation_lane=observation_lane,
        extras={"odds_source": odds_source, "exchange_errors": errors[:5]},
    )


def telemetry_balance_for_date(
    card_date: str,
    *,
    observation_lane: bool = False,
    database: Any = None,
) -> TelemetryBalanceReport:
    from pathlib import Path

    from hibs_racing.config import db_path

    db = database or db_path(load_config())
    db_path_obj = Path(db) if not isinstance(db, Path) else db
    manifest = latest_manifest_for_date(card_date, database=db_path_obj)
    if not manifest:
        pending = f"No refresh manifest for {card_date} — run refresh-cards"
        if observation_lane:
            return TelemetryBalanceReport(
                passed=True,
                card_date=card_date,
                manifest_id=None,
                checks=[
                    {
                        "name": "manifest_present",
                        "passed": True,
                        "detail": f"{pending} (advisory — observation lane)",
                    }
                ],
                timings_ms={},
                shares_pct={},
                matchbook_coverage_ratio=None,
                total_ms=0.0,
                message=f"Telemetry balance pending — {pending}",
                observation_lane=observation_lane,
            )
        return TelemetryBalanceReport(
            passed=False,
            card_date=card_date,
            manifest_id=None,
            checks=[
                {
                    "name": "manifest_present",
                    "passed": False,
                    "detail": pending,
                }
            ],
            timings_ms={},
            shares_pct={},
            matchbook_coverage_ratio=None,
            total_ms=0.0,
            message="Telemetry balance FAILED — no manifest.",
            observation_lane=observation_lane,
        )
    return evaluate_telemetry_balance(
        refresh_payload={"card_dates": [card_date], "card_date": card_date},
        manifest=manifest,
        observation_lane=observation_lane,
    )


def record_telemetry_balance(
    refresh_payload: dict[str, Any],
    *,
    manifest_id: str | None = None,
    observation_lane: bool = False,
    database: Any = None,
) -> TelemetryBalanceReport:
    """Evaluate and append ledger event for daily telemetry balance."""
    from pathlib import Path

    from hibs_racing.config import db_path
    from hibs_racing.institutional.ledger_events import append_ledger_event

    report = evaluate_telemetry_balance(
        refresh_payload=refresh_payload,
        observation_lane=observation_lane,
    )
    mid = manifest_id or refresh_payload.get("manifest_id")
    db = database or db_path(load_config())
    append_ledger_event(
        event_type="telemetry_balance",
        manifest_id=mid,
        payload=report.to_dict(),
        database=Path(db) if not isinstance(db, Path) else db,
    )
    return report
