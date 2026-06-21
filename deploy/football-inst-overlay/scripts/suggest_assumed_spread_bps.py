#!/usr/bin/env python3
"""Suggest TRADING_ASSUMED_SPREAD_BPS from live spread-slippage audit JSONL."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int(math.ceil(q * len(ordered))) - 1))
    return ordered[idx]


def load_live_spreads(audit_path: Path) -> list[float]:
    spreads: list[float] = []
    if not audit_path.is_file():
        return spreads
    with audit_path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            val = row.get("live_spread_bps")
            if val is None:
                continue
            try:
                spreads.append(float(val))
            except (TypeError, ValueError):
                continue
    return spreads


def suggest_spread_bps(
    spreads: list[float],
    *,
    floor_bps: float = 5.0,
    ceiling_bps: float = 50.0,
    quantile: float = 0.95,
    pad_bps: float = 2.0,
) -> dict:
    p50 = _percentile(spreads, 0.50)
    p95 = _percentile(spreads, quantile)
    suggested = None
    if p95 is not None:
        suggested = round(min(ceiling_bps, max(floor_bps, p95 + pad_bps)), 1)
    return {
        "n_observations": len(spreads),
        "live_spread_p50_bps": round(p50, 2) if p50 is not None else None,
        "live_spread_p95_bps": round(p95, 2) if p95 is not None else None,
        "suggested_assumed_spread_bps": suggested,
        "quantile": quantile,
        "pad_bps": pad_bps,
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Suggest assumed spread bps from spread audit JSONL.")
    p.add_argument(
        "--audit",
        default="/var/log/trading-core/spread_slippage.jsonl",
        help="Path to spread slippage audit JSONL",
    )
    p.add_argument("--json", action="store_true", help="Emit JSON only")
    args = p.parse_args()
    spreads = load_live_spreads(Path(args.audit))
    out = suggest_spread_bps(spreads)
    if args.json:
        print(json.dumps(out, indent=2))
    else:
        print(f"observations: {out['n_observations']}")
        print(f"live p50: {out['live_spread_p50_bps']} bps")
        print(f"live p95: {out['live_spread_p95_bps']} bps")
        print(f"suggested TRADING_ASSUMED_SPREAD_BPS: {out['suggested_assumed_spread_bps']}")
    return 0 if out["n_observations"] > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
