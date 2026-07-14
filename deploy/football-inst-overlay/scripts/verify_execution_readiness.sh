#!/usr/bin/env bash
# Execution + automation readiness — infra paper mode vs live staking.
#
# Exit 0 = automation GREEN (services, crons, paper path)
# Exit 1 = critical infra failure
# Exit 2 = infra OK but live execution not armed (expected analytics default)
#
#   bash /opt/hibs-bet/scripts/verify_execution_readiness.sh
#   bash /opt/hibs-bet/scripts/verify_execution_readiness.sh --json
#   HIBS_REQUIRE_LIVE_EXECUTION=1 bash ...  # exit 1 if live not armed
set -euo pipefail

APP="${DEPLOY_PATH:-/opt/hibs-bet}"
RACING="${HIBS_RACING_DEPLOY_PATH:-/opt/hibs-racing}"
JSON=0
REQUIRE_LIVE=0

for arg in "$@"; do
  case "${arg}" in
    --json) JSON=1 ;;
  esac
done
[[ "${HIBS_REQUIRE_LIVE_EXECUTION:-0}" == "1" ]] && REQUIRE_LIVE=1

fail=0
warn=0
checks=()

add() {
  local status="$1" name="$2" detail="$3"
  checks+=("${status}|${name}|${detail}")
  [[ "${status}" == "FAIL" ]] && fail=1
  [[ "${status}" == "WARN" ]] && warn=1
}

probe() {
  curl -sS -o /dev/null -w '%{http_code}' --max-time "${2:-8}" "$1" 2>/dev/null || echo 000
}

fb="$(probe http://127.0.0.1:8000/api/ping)"
rc="$(probe http://127.0.0.1:5003/api/ping)"
[[ "${fb}" == "200" ]] && add OK football_ping "HTTP ${fb}" || add FAIL football_ping "HTTP ${fb}"
[[ "${rc}" == "200" ]] && add OK racing_ping "HTTP ${rc}" || add FAIL racing_ping "HTTP ${rc}"

for svc in hibs-bet hibs-racing; do
  st="$(systemctl is-active "${svc}" 2>/dev/null || echo unknown)"
  [[ "${st}" == "active" ]] && add OK "service_${svc}" "${st}" || add FAIL "service_${svc}" "${st}"
done

cr="$(crontab -u www-data -l 2>/dev/null || true)"
echo "${cr}" | grep -q 'infra fallback' && add OK cron_infra_fallback installed || add WARN cron_infra_fallback missing
echo "${cr}" | grep -q 'brier circuit breaker' && add OK cron_brier_circuit installed || add WARN cron_brier_circuit missing
echo "${cr}" | grep -q 'hands-off' && add OK cron_hands_off installed || add WARN cron_hands_off missing
echo "${cr}" | grep -q 'pre-race poll' && add OK cron_pre_race_poll installed || add WARN cron_pre_race_poll missing

PY="${APP}/.venv/bin/python3"
[[ -x "${PY}" ]] || PY=python3
if PYTHONPATH="${APP}/src:${RACING}/src" "${PY}" -c "
from hibs_predictor.safety.brier_circuit_breaker import calibration_safety_summary
import json
print(json.dumps(calibration_safety_summary()))
" 2>/dev/null; then
  cal="$(PYTHONPATH="${APP}/src:${RACING}/src" "${PY}" -c "
from hibs_predictor.safety.brier_circuit_breaker import calibration_safety_summary
import json
print(json.dumps(calibration_safety_summary()))
")"
  if echo "${cal}" | grep -q '"execution_lockout_active": true'; then
    add WARN brier_circuit lockout_active
  else
    add OK brier_circuit closed
  fi
else
  add WARN brier_circuit unavailable
fi

exec_disabled=1
live=0
if PYTHONPATH="${RACING}/src" "${PY}" -c "
from hibs_racing.live.execution_config import EXECUTION_DISABLED
import os
print('disabled=' + str(int(EXECUTION_DISABLED)))
print('live=' + str(int(os.getenv('HIBS_EXECUTION_LIVE','').strip().lower() in ('1','true','yes'))))
" 2>/dev/null | tee /tmp/hibs_exec_mode.txt >/dev/null; then
  grep -q 'disabled=1' /tmp/hibs_exec_mode.txt && exec_disabled=1 || exec_disabled=0
  grep -q 'live=1' /tmp/hibs_exec_mode.txt && live=1 || live=0
fi

if [[ "${exec_disabled}" -eq 1 ]]; then
  add OK execution_mode analytics "EXECUTION_DISABLED — paper/shadow only"
elif [[ "${live}" -eq 1 ]]; then
  add OK execution_mode live_armed "HIBS_EXECUTION_LIVE=1"
else
  add WARN execution_mode dry_router "router enabled but HIBS_EXECUTION_LIVE unset"
fi

[[ "${REQUIRE_LIVE}" -eq 1 && ( "${exec_disabled}" -eq 1 || "${live}" -eq 0 ) ]] && fail=1

if [[ "${JSON}" -eq 1 ]]; then
  printf '{"fail":%s,"warn":%s,"checks":[' "${fail}" "${warn}"
  first=1
  for row in "${checks[@]}"; do
    IFS='|' read -r st name detail <<<"${row}"
    [[ "${first}" -eq 1 ]] || printf ','
    first=0
    printf '{"status":"%s","name":"%s","detail":"%s"}' "${st}" "${name}" "${detail}"
  done
  printf ']}\n'
else
  echo "=== execution readiness ==="
  for row in "${checks[@]}"; do
    IFS='|' read -r st name detail <<<"${row}"
    printf "%-6s %-24s %s\n" "${st}" "${name}" "${detail}"
  done
fi

if [[ "${fail}" -ne 0 ]]; then exit 1; fi
if [[ "${warn}" -ne 0 && "${REQUIRE_LIVE}" -eq 0 ]]; then exit 2; fi
exit 0
