#!/usr/bin/env python3
"""Offline gate profile A/B — baseline vs trial_domestic_cups (no API)."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    ap = argparse.ArgumentParser(description="Compare forward evidence gate profiles (offline).")
    ap.add_argument("--json", action="store_true", help="Emit JSON only")
    ap.add_argument("--days", type=int, default=90, help="CLV window for settled-row slice")
    ap.add_argument("--min-bets", type=int, default=5, help="Minimum settled rows for slice note")
    ap.add_argument("--exhaustive", action="store_true", help="Include gate_profile_compare env profiles")
    args = ap.parse_args()

    from hibs_predictor.forward_evidence import forward_evidence_gates
    from hibs_predictor.gate_profile_compare import compare_summary, list_gate_profiles

    profiles: dict[str, dict] = {}
    for label, trial in (("baseline_all_leagues", "0"), ("trial_domestic_cups", "1")):
        os.environ["HIBS_F9_TRIAL_LEAGUES_ONLY"] = trial
        profiles[label] = forward_evidence_gates()

    settled = compare_summary(days=args.days, min_bets=args.min_bets)
    if args.exhaustive:
        settled["env_profiles"] = list_gate_profiles()

    out = {
        "profiles": profiles,
        "settled_slice": settled,
        "diff_buyer_ready": {
            k: profiles[k].get("buyer_ready") for k in profiles
        },
        "note": "Calendar-bound gates (F7–F9) need VPS snapshots + settled rows; script is structural A/B only.",
    }
    if args.json:
        print(json.dumps(out, indent=2, default=str))
    else:
        print("==> compare_gate_profiles")
        for name, g in profiles.items():
            print(f"  {name}: buyer_ready={g.get('buyer_ready')} grade={g.get('evidence_grade')} matchdays_7d={g.get('matchdays_7d')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
