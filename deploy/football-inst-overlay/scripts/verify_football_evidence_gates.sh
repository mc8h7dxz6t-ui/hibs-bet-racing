#!/usr/bin/env bash
# Forward evidence gate verify — internal ops checklist (not external product certification).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="${ROOT}/src${PYTHONPATH:+:$PYTHONPATH}"

python3 - <<'PY'
import sys
from hibs_predictor.forward_evidence import forward_evidence_gates

g = forward_evidence_gates()
honesty = (g.get("honesty") or {}).get("what_this_is", "")
print("==> verify_football_evidence_gates")
print("==> Internal evidence gates (sports research — NOT enterprise platform certification)")
if honesty:
    print(f"    {honesty}")
print(f"since_deploy: {g.get('since_deploy') or g.get('since_deploy_iso')}")
print(f"matchdays_7d: {g.get('matchdays_7d')}")
print(f"evidence_grade: {g.get('evidence_grade')} (ops letter — not alpha proof)")
print(f"evidence_gates_complete: {g.get('evidence_gates_complete', g.get('buyer_ready'))}")
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

complete = g.get("evidence_gates_complete", g.get("buyer_ready"))
if not complete:
    sys.exit(1)
PY
