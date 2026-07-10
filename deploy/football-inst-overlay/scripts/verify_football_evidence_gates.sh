#!/usr/bin/env bash
# Industry-standard forward evidence gate verify (F1–F3 engineering, F7–F9 buyer, F9b/c informational).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="${ROOT}/src${PYTHONPATH:+:$PYTHONPATH}"

python3 - <<'PY'
import sys
from hibs_predictor.forward_evidence import forward_evidence_gates

g = forward_evidence_gates()
print("==> verify_football_evidence_gates")
print("==> Forward evidence gates (B2B buyer_ready)")
print(f"since_deploy: {g.get('since_deploy') or g.get('since_deploy_iso')}")
print(f"matchdays_7d: {g.get('matchdays_7d')}")
print(f"evidence_grade: {g.get('evidence_grade')}")
print(f"buyer_ready: {g.get('buyer_ready')}")
print()

by_id = {row["id"]: row for row in (g.get("gates") or [])}
for gid in (
    "F1_audit",
    "F2_clv",
    "F3_cron",
    "F7_forward_capture_7d",
    "F7b_scored_capture_since_deploy",
    "F8_clv_sample",
    "F9_clv_beat_close",
    "F9b_clv_beat_close_fair_shin",
    "F9c_clv_benchmark_tier",
):
    row = by_id.get(gid) or {}
    passed = row.get("pass")
    val = row.get("actual")
    need = row.get("threshold", "")
    hint = row.get("message", "")
    tag = "PASS" if passed else "FAIL"
    if gid in ("F9b_clv_beat_close_fair_shin", "F9c_clv_benchmark_tier"):
        need = "informational — not buyer pass/fail"
    print(f"  [{tag}] {gid}: {val!r} (need {need})")
    if hint:
        print(f"         {hint}")

print()
print("Next actions:")
for a in g.get("next_actions") or []:
    print(f"  - {a}")

if not g.get("buyer_ready"):
    sys.exit(1)
PY
