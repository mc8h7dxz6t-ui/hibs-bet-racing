#!/usr/bin/env python3
"""Trading Day-15 economic gate — PASS / FAIL / INCONCLUSIVE (AAPL equity lane)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from hibs_predictor.trading_core.promotion_scorecard import (  # noqa: E402
    ScorecardThresholds,
    spread_delta_percentiles,
)


def _load_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    rows: list[dict] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            try:
                row = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                rows.append(row)
    return rows


def _equity_stream_days(scan_rows: list[dict], *, symbol: str = "AAPL") -> int:
    days: set[str] = set()
    for row in scan_rows:
        if str(row.get("symbol", "")).upper() != symbol.upper():
            continue
        ts = str(row.get("ts") or row.get("timestamp") or "")[:10]
        if ts:
            days.add(ts)
    return len(days)


def _symbol_status_counts(scan_rows: list[dict], *, symbol: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    sym = symbol.upper()
    for row in scan_rows:
        if str(row.get("symbol", "")).upper() != sym:
            continue
        status = str(row.get("status") or "UNKNOWN")
        counts[status] = counts.get(status, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def _max_abs_ofi(scan_rows: list[dict], *, symbol: str) -> float | None:
    sym = symbol.upper()
    peak: float | None = None
    for row in scan_rows:
        if str(row.get("symbol", "")).upper() != sym:
            continue
        details = row.get("details") or {}
        if not isinstance(details, dict):
            continue
        raw = details.get("ofi")
        if raw is None:
            continue
        try:
            value = abs(float(raw))
        except (TypeError, ValueError):
            continue
        peak = value if peak is None else max(peak, value)
    return peak


def _resolve_audit_path(
    trading_root: Path,
    *,
    env_key: str,
    explicit: str | None,
    fallback_names: tuple[str, ...],
) -> Path:
    """Resolve shadow JSONL path (env → explicit → known filenames under data/)."""
    data = trading_root / "data"
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    env_raw = os.environ.get(env_key, "").strip()
    if env_raw:
        candidates.append(Path(env_raw))
    candidates.extend(data / name for name in fallback_names)

    seen: set[Path] = set()
    for raw in candidates:
        path = raw if raw.is_absolute() else trading_root / raw
        if path in seen:
            continue
        seen.add(path)
        if path.is_file():
            return path
    return data / fallback_names[0]


def evaluate_day15(
    *,
    trading_root: Path,
    symbol: str = "AAPL",
    thresholds: ScorecardThresholds | None = None,
    strategy_audit: str | None = None,
    spread_audit: str | None = None,
) -> dict:
    t = thresholds or ScorecardThresholds()
    scan_path = _resolve_audit_path(
        trading_root,
        env_key="TRADING_STRATEGY_AUDIT",
        explicit=strategy_audit,
        fallback_names=(
            "strategy_scan_audit.jsonl",
            "strategy_scan_shadow_calibration.jsonl",
            "strategy_scan_paper.jsonl",
        ),
    )
    spread_path = _resolve_audit_path(
        trading_root,
        env_key="TRADING_SPREAD_AUDIT",
        explicit=spread_audit,
        fallback_names=(
            "spread_slippage_audit.jsonl",
            "spread_slippage_shadow_calibration.jsonl",
            "spread_slippage_paper.jsonl",
        ),
    )
    scan_rows = _load_jsonl(scan_path)
    spread_stats = spread_delta_percentiles(spread_path)
    spread_limit = max(t.spread_delta_p95_max_bps, t.assumed_spread_bps + 5.0)

    would_route = [
        r
        for r in scan_rows
        if r.get("status") == "SHADOW_WOULD_ROUTE"
        and str(r.get("symbol", "")).upper() == symbol.upper()
    ]
    stream_days = _equity_stream_days(scan_rows, symbol=symbol)
    aapl_status_counts = _symbol_status_counts(scan_rows, symbol=symbol)
    max_abs_ofi = _max_abs_ofi(scan_rows, symbol=symbol)
    total_would_route = sum(
        1 for r in scan_rows if r.get("status") == "SHADOW_WOULD_ROUTE"
    )
    p95 = spread_stats.get("p95")
    recon_drifts = None
    metrics_path = trading_root / "data" / "metrics_snapshot.json"
    if metrics_path.is_file():
        try:
            recon_drifts = json.loads(metrics_path.read_text(encoding="utf-8")).get(
                "trading_reconciliation_drifts_total"
            )
        except Exception:
            recon_drifts = None

    verdict = "INCONCLUSIVE"
    reasons: list[str] = []
    if stream_days < 3:
        reasons.append(f"<3 equity stream days for {symbol} (have {stream_days})")
        verdict = "INCONCLUSIVE"
    elif not would_route:
        reasons.append(f"no SHADOW_WOULD_ROUTE rows for {symbol}")
        verdict = "FAIL"
    elif p95 is None:
        reasons.append("no spread JSONL rows for p95")
        verdict = "FAIL"
    elif float(p95) > spread_limit:
        reasons.append(f"spread p95 {p95} > limit {spread_limit}")
        verdict = "FAIL"
    elif recon_drifts not in (None, 0, 0.0, "0"):
        reasons.append(f"reconciliation drifts={recon_drifts}")
        verdict = "FAIL"
    else:
        reasons.append(f">=1 would-route on {symbol}; spread p95 {p95} <= {spread_limit}")
        verdict = "PASS"

    return {
        "verdict": verdict,
        "symbol": symbol,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "would_route_count": len(would_route),
        "equity_stream_days": stream_days,
        "spread_p95_bps": p95,
        "spread_limit_bps": spread_limit,
        "spread_row_count": int(spread_stats.get("count") or 0),
        "scan_row_count": len(scan_rows),
        "recon_drifts": recon_drifts,
        "aapl_status_counts": aapl_status_counts,
        "max_abs_ofi": max_abs_ofi,
        "total_shadow_would_route_all_symbols": total_would_route,
        "reasons": reasons,
        "artifacts": {
            "scan": str(scan_path),
            "spread": str(spread_path),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Trading Day-15 gate evaluator")
    parser.add_argument(
        "--trading-root",
        default=os.environ.get("TRADING_INSTALL_ROOT", "/opt/trading-core"),
    )
    parser.add_argument("--symbol", default="AAPL")
    parser.add_argument(
        "--strategy-audit",
        default=os.environ.get("TRADING_STRATEGY_AUDIT"),
        help="Strategy scan JSONL (default: TRADING_STRATEGY_AUDIT or data/strategy_scan_audit.jsonl)",
    )
    parser.add_argument(
        "--spread-audit",
        default=os.environ.get("TRADING_SPREAD_AUDIT"),
        help="Spread slippage JSONL (default: TRADING_SPREAD_AUDIT or data/spread_slippage_audit.jsonl)",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = evaluate_day15(
        trading_root=Path(args.trading_root),
        symbol=args.symbol,
        strategy_audit=args.strategy_audit,
        spread_audit=args.spread_audit,
    )
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"Day-15 verdict: {report['verdict']}")
        for r in report["reasons"]:
            print(f"  - {r}")
        print(
            f"  would_route={report['would_route_count']} "
            f"stream_days={report['equity_stream_days']} "
            f"spread_p95={report['spread_p95_bps']}"
        )
        if report.get("aapl_status_counts"):
            print(f"  {symbol} status breakdown: {report['aapl_status_counts']}")
        if report.get("max_abs_ofi") is not None:
            print(f"  {symbol} max |OFI| observed: {report['max_abs_ofi']:.4f}")
        if report.get("total_shadow_would_route_all_symbols"):
            print(
                "  total SHADOW_WOULD_ROUTE (all symbols): "
                f"{report['total_shadow_would_route_all_symbols']}"
            )
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
