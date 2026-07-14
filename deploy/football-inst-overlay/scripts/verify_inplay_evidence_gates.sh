#!/usr/bin/env bash
# In-play institutional evidence gates (I1–I5) — exit 0 when buyer_ready.
# Usage:
#   ./scripts/verify_inplay_evidence_gates.sh
#   ./scripts/verify_inplay_evidence_gates.sh --json
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"
# shellcheck source=lib_hibs_python.sh
source "${ROOT}/scripts/lib_hibs_python.sh"
JSON_ONLY=0
[[ "${1:-}" == "--json" ]] && JSON_ONLY=1

APP="${DEPLOY_PATH:-${ROOT}}"
hibs_python_env "${APP}"
PY="$(hibs_resolve_python "${APP}")"
export FVE_API_URL="${FVE_API_URL:-http://127.0.0.1:8010}"

OUT="$("${PY}" -c "
from hibs_predictor.inplay_evidence import inplay_evidence_gates
import json
print(json.dumps(inplay_evidence_gates(), indent=2, default=str))
")"

if [[ "${JSON_ONLY}" -eq 1 ]]; then
  echo "${OUT}"
  echo "${OUT}" | "${PY}" -c "import json,sys; d=json.load(sys.stdin); sys.exit(0 if d.get('buyer_ready') else 1)"
  exit $?
fi

echo "==> In-play evidence gates (buyer_ready)"
echo "${OUT}" | "${PY}" -c "
import json, sys
d = json.load(sys.stdin)
print('base_url:', d.get('base_url'))
print('integration_enabled:', d.get('integration_enabled'))
print('since_deploy_iso:', d.get('since_deploy_iso'))
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
