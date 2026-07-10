#!/usr/bin/env python3
"""F7 capture regression alert — cron target after morning seed."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    from hibs_predictor.forward_evidence import forward_evidence_gates

    g = forward_evidence_gates()
    matchdays = int(g.get("matchdays_7d") or 0)
    by_id = {row["id"]: row for row in (g.get("gates") or [])}
    f7 = by_id.get("F7_forward_capture_7d") or {}
    cap = f7.get("coverage_pct")

    if matchdays < 3:
        print(f"INFO: F7 deferred — matchdays={matchdays} < 3 (calendar-bound)")
        return 0

    if cap is None:
        print("ALERT: F7 capture rate missing after 3+ matchdays — run seed/backfill")
        return 1

    pct = float(cap)
    if pct < 50.0:
        print(f"ALERT: F7 capture regression {pct}% < 50% (matchdays={matchdays})")
        return 1

    print(f"OK: F7 capture {pct}% (matchdays={matchdays})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
