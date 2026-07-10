#!/usr/bin/env bash
# Personal staking green lights — football + racing + FVE (facts, not sales).
#
#   bash /opt/hibs-bet/scripts/verify_personal_staking_greenlights.sh
#   bash /opt/hibs-bet/scripts/verify_personal_staking_greenlights.sh --json
set -euo pipefail

APP="${DEPLOY_PATH:-/opt/hibs-bet}"
PY="${APP}/.venv/bin/python3"
[[ -x "${PY}" ]] || PY="python3"
export PYTHONPATH="${APP}/src" HOME="${APP}"

JSON_ONLY=0
[[ "${1:-}" == "--json" ]] && JSON_ONLY=1

OUT="$("${PY}" -c "
from hibs_predictor.personal_staking_gates import personal_staking_report
import json
print(json.dumps(personal_staking_report(), indent=2, default=str))
")"

if [[ "${JSON_ONLY}" -eq 1 ]]; then
  echo "${OUT}"
  exit 0
fi

echo "==> Personal staking green lights (internal — not financial advice)"
echo "${OUT}" | "${PY}" -c "
import json, sys
d = json.load(sys.stdin)
print('any_lane_staking_green_light:', d.get('any_lane_staking_green_light'))
print('fve_operational:', d.get('fve_operational'))
print()
for lane, rep in (d.get('lanes') or {}).items():
    if lane == 'fve':
        print(f'  [{lane}] operational={rep.get(\"operational\")} fixtures={rep.get(\"fixture_count\")}')
        continue
    gl = rep.get('personal_green_light')
    mark = 'GREEN' if gl else 'WAIT'
    print(f'  [{mark}] {lane}: staking_allowed={rep.get(\"staking_allowed\")}')
    for b in rep.get('blockers') or []:
        print(f'         blocker: {b}')
    for n in rep.get('notes') or []:
        print(f'         note: {n}')
print()
print(d.get('disclaimer', ''))
"
