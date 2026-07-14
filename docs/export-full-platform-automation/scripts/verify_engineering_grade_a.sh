#!/usr/bin/env bash
# Exit 0 only when institutional_readiness.engineering_grade == A (zero warnings, no blocks).
#
#   ./scripts/verify_engineering_grade_a.sh
#   ./scripts/verify_engineering_grade_a.sh --json
#   DEPLOY_HOST=87.106.100.52 ./scripts/verify_engineering_grade_a.sh --remote
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"
# shellcheck source=lib_hibs_python.sh
source "${ROOT}/scripts/lib_hibs_python.sh"

JSON=0
REMOTE=0
for arg in "$@"; do
  case "${arg}" in
    --json) JSON=1 ;;
    --remote) REMOTE=1 ;;
  esac
done

if [[ "${REMOTE}" -eq 1 ]]; then
  HOST="${DEPLOY_HOST:-87.106.100.52}"
  USER="${DEPLOY_USER:-root}"
  APP="${DEPLOY_PATH:-/opt/hibs-bet}"
  exec ssh -o BatchMode=yes -o ConnectTimeout=25 "${USER}@${HOST}" \
    "bash '${APP}/scripts/verify_engineering_grade_a.sh' ${JSON:+--json}"
fi

APP="${DEPLOY_PATH:-${ROOT}}"
hibs_python_env "${APP}"
PY="$(hibs_resolve_python "${APP}")"

OUT="$("${PY}" -c "
from hibs_predictor.institutional_readiness import readiness_dict
import json
print(json.dumps(readiness_dict(), indent=2, default=str))
")"

if [[ "${JSON}" -eq 1 ]]; then
  echo "${OUT}"
else
  echo "==> Engineering grade A verify"
  echo "${OUT}" | "${PY}" -c "
import json, sys
d = json.load(sys.stdin)
print('engineering_grade:', d.get('engineering_grade'))
print('evidence_grade:', d.get('evidence_grade'))
print('buyer_ready:', d.get('buyer_ready'))
for msg in d.get('blocking_issues') or []:
    print('  BLOCK:', msg)
for msg in d.get('warnings') or []:
    print('  WARN:', msg)
"
fi

echo "${OUT}" | "${PY}" -c "
import json, sys
d = json.load(sys.stdin)
grade = d.get('engineering_grade')
blocks = d.get('blocking_issues') or []
warns = d.get('warnings') or []
ok = grade == 'A' and not blocks and not warns
sys.exit(0 if ok else 1)
"
