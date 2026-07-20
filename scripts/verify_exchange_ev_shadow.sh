#!/usr/bin/env bash
# Verify exchange place EV is in shadow (Gate3) — production EW until coverage proof.
#
#   ./scripts/verify_exchange_ev_shadow.sh
#   ./scripts/verify_exchange_ev_shadow.sh --json
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"
# shellcheck disable=SC1091
source "${ROOT}/scripts/_lib.sh"

JSON=0
[[ "${1:-}" == "--json" ]] && JSON=1

activate_venv
load_env

status="$("${ROOT}/.venv/bin/hibs-racing" exchange-ev-status 2>/dev/null)" || {
  if [[ "${JSON}" -eq 1 ]]; then
    echo '{"ok": false, "message": "exchange-ev-status CLI unavailable"}'
  else
    echo "FAIL: exchange-ev-status CLI unavailable"
  fi
  exit 1
}

ok="$("${ROOT}/.venv/bin/python3" -c "
import json, sys
d = json.loads(sys.argv[1])
shadow = bool(d.get('exchange_ev_shadow'))
prod = bool(d.get('exchange_ev_production'))
sys.exit(0 if shadow and not prod else 1)
" "${status}" 2>/dev/null && echo 1 || echo 0)"

if [[ "${JSON}" -eq 1 ]]; then
  "${ROOT}/.venv/bin/python3" -c "
import json, sys
d = json.loads(sys.argv[1])
d['ok'] = bool(${ok})
print(json.dumps(d, indent=2))
" "${status}"
  exit "$([[ "${ok}" -eq 1 ]] && echo 0 || echo 1)"
fi

echo "==> Exchange EV shadow (Gate3)"
echo "${status}" | "${ROOT}/.venv/bin/python3" -c "
import json, sys
d = json.load(sys.stdin)
print('  shadow:', d.get('exchange_ev_shadow'))
print('  production:', d.get('exchange_ev_production'))
print('  coverage:', d.get('exchange_place_coverage_pct'), '%')
print('  message:', d.get('message'))
"
if [[ "${ok}" -eq 1 ]]; then
  echo "  OK — shadow on, production off"
  exit 0
fi
echo "  FAIL — need HIBS_EXCHANGE_EV_SHADOW=1 and HIBS_EXCHANGE_EV_PRODUCTION=0"
exit 1
