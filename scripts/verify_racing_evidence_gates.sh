#!/usr/bin/env bash
# Racing institutional evidence gates (R1–R7) — exit 0 when buyer_ready.
#
#   bash scripts/verify_racing_evidence_gates.sh
#   bash scripts/verify_racing_evidence_gates.sh --json
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${ROOT}/.venv/bin/python3"
[[ -x "${PY}" ]] || PY="python3"
export PYTHONPATH="${ROOT}/src"

JSON_ONLY=0
[[ "${1:-}" == "--json" ]] && JSON_ONLY=1

OUT="$("${PY}" -c "
from hibs_racing.evidence_gates import racing_evidence_gates
import json
print(json.dumps(racing_evidence_gates(), indent=2, default=str))
")"

if [[ "${JSON_ONLY}" -eq 1 ]]; then
  echo "${OUT}"
  echo "${OUT}" | "${PY}" -c "import json,sys; d=json.load(sys.stdin); sys.exit(0 if d.get('buyer_ready') else 1)"
  exit $?
fi

echo "==> Racing evidence gates (local buyer_ready)"
echo "${OUT}" | "${PY}" -c "
import json, sys
d = json.load(sys.stdin)
print('source:', d.get('source'))
print('evidence_grade:', d.get('evidence_grade'))
print('buyer_ready:', d.get('buyer_ready'))
print()
for g in d.get('gates', []):
    mark = 'PASS' if g.get('pass') else 'FAIL'
    print(f\"  [{mark}] {g.get('id')}: {g.get('actual')} (need {g.get('threshold')})\")
    if g.get('message') and not g.get('pass'):
        print(f\"         {g.get('message')}\")
if d.get('next_actions'):
    print()
    print('Next actions:')
    for a in d['next_actions']:
        print(f\"  - {a}\")
sys.exit(0 if d.get('buyer_ready') else 1)
"
