#!/bin/bash
# Pre-flight for local racing observation lane (Jun 4–10).
# Exit 0 = hard gates pass (lane armed). Exit 1 = blocking fail. Exit 2 = soft warn only.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/_lib.sh"

SMOKE=0
for arg in "$@"; do
  case "${arg}" in
    --smoke) SMOKE=1 ;;
    -h|--help)
      echo "Usage: $0 [--smoke]"
      echo "  --smoke  Run full daily_refresh.sh (morning cards recommended)"
      exit 0
      ;;
  esac
done

activate_venv
load_env

FAIL=0
WARN=0

pass() { echo "PASS: $*"; }
fail() { echo "FAIL: $*" >&2; FAIL=1; }
warn() { echo "WARN: $*" >&2; WARN=1; }

echo "=== hibs-racing observation lane pre-flight ==="
echo "repo: ${ROOT}"
echo "utc:  $(date -u +%Y-%m-%dT%H:%M:%SZ)"

# 1. Credentials
if [[ -n "${RACING_API_USERNAME:-}" && -n "${MATCHBOOK_USERNAME:-}" ]]; then
  pass "API credentials present in .env"
else
  fail "RACING_API_USERNAME or MATCHBOOK_USERNAME missing in .env"
fi

# 2. raceform.db
RFDB="${RACEFORM_DB_PATH:-${HOME}/raceform.db}"
RFDB="${RFDB/#\~/$HOME}"
if [[ -f "${RFDB}" ]]; then
  pass "raceform.db readable at ${RFDB}"
else
  fail "raceform.db not found at ${RFDB} (set RACEFORM_DB_PATH in .env)"
fi

# 3. NA hotfix present (Jun 3 cron crash)
if grep -q '_present(row.get("enrich_source"))' "${ROOT}/src/hibs_racing/cards/data_quality.py" 2>/dev/null; then
  pass "pandas NA data_quality hotfix present"
else
  fail "missing NA hotfix in data_quality.py — pull commit 47ca539 or apply §3.6 fix"
fi

# 4. Cron posture
CRON="$(crontab -l 2>/dev/null || true)"
if echo "${CRON}" | grep -qE 'hibs-racing/scripts/(daily_refresh|cron_refresh_wrapper)\.sh'; then
  pass "daily_refresh cron installed"
else
  warn "daily_refresh cron not installed — run: bash scripts/install_observation_cron.sh"
fi
if echo "${CRON}" | grep -v '^#' | grep -q 'weekly_retrain.sh'; then
  fail "weekly_retrain.sh is active in crontab — disable during observation freeze"
else
  pass "weekly_retrain frozen or absent from crontab"
fi

# 5. Log directory
mkdir -p "${LOG_DIR}"
if [[ -d "${LOG_DIR}" ]]; then
  pass "logs directory ${LOG_DIR}"
else
  fail "cannot create logs directory"
fi

# 6. Mac sleep (informational)
if [[ "$(uname -s)" == "Darwin" ]]; then
  if pmset -g custom 2>/dev/null | grep -q 'sleep 0'; then
    pass "macOS sleep disabled on power (or sleep 0)"
  else
    warn "macOS may sleep before 06:00 cron — use Energy settings or manual daily_refresh on wake (§3.7)"
  fi
fi

# 7. Matchbook dry-run (soft fail when no GB/IRE cards off-hours)
echo "--- dry-run-quotes ---"
set +e
bash "${SCRIPT_DIR}/daily_refresh.sh" --dry-run-quotes >/dev/null 2>&1
DRY_RC=$?
set -e
DRY_LOG="$(log_file dry-run-quotes)"
DRY_TAIL="$(tail -40 "${DRY_LOG}" 2>/dev/null || true)"
echo "${DRY_TAIL}" | tail -15
DRY_LAST="$(tail -1 "${DRY_LOG}" 2>/dev/null | tr -d '\r' || true)"
if [[ "${DRY_LAST}" == "OK: dry-run-quotes" ]]; then
  pass "Matchbook dry-run completed"
elif echo "${DRY_TAIL}" | grep -q '"ok": true'; then
  pass "Matchbook dry-run completed"
elif echo "${DRY_TAIL}" | grep -qiE 'no quotes|no GB/IRE markets|no runners in card'; then
  warn "Matchbook dry-run: no card markets now (expected off-hours) — retry after 06:00 UK"
else
  fail "Matchbook dry-run failed (rc=${DRY_RC}) — see logs/dry-run-quotes.log"
fi

# 7b. Telemetry balance on today's manifest (institutional++)
echo "--- telemetry-balance ---"
TB_PASS="$(hibs-racing institutional-check --days 1 --card-date "$(date -u +%F)" --observation-lane 2>/dev/null | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(d.get('telemetry_balance', {}).get('passed', False))
" 2>/dev/null || echo False)"
if [[ "${TB_PASS}" == "True" ]]; then
  pass "telemetry balance OK (Racing API + Matchbook mix)"
else
  warn "telemetry balance soft-fail — run refresh-cards after 06:00 UK or check Matchbook coverage"
fi

# 8. Institutional check (snapshot FAIL is soft during observation start)
echo "--- institutional-check ---"
set +e
INST_JSON="$(hibs-racing institutional-check --days 14 --card-date "$(date -u +%F)" --observation-lane 2>/dev/null)"
INST_RC=$?
set -e
RECON_CLEAN="$(printf '%s' "${INST_JSON}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('paper_reconciliation',{}).get('is_clean', False))" 2>/dev/null || echo False)"
if [[ ${INST_RC} -eq 0 ]]; then
  pass "institutional-check passed"
elif [[ "${RECON_CLEAN}" == "True" ]]; then
  SNAP_OK="$(printf '%s' "${INST_JSON}" | python3 -c "
import sys, json
d = json.load(sys.stdin)
cov = d.get('snapshot_coverage') or {}
print(cov.get('today_snapshot', False))
" 2>/dev/null || echo False)"
  if [[ "${SNAP_OK}" == "True" ]]; then
    pass "institutional-check passed (recon + snapshot; gate regression advisory)"
  else
    warn "institutional-check: recon clean but snapshot missing — run: hibs-racing refresh-cards --paper"
  fi
else
  fail "institutional-check failed with reconciliation issues"
fi

# 9. Optional full smoke
if [[ ${SMOKE} -eq 1 ]]; then
  echo "--- full daily_refresh smoke ---"
  set +e
  bash "${SCRIPT_DIR}/daily_refresh.sh"
  SMOKE_RC=$?
  set -e
  # Success = daily_refresh exit 0 (prints "Daily refresh completed successfully." on stdout).
  # Do not require cron_daily.log — that file is only appended when cron redirects stdout.
  if [[ ${SMOKE_RC} -eq 0 ]]; then
    pass "full smoke: Daily refresh completed successfully"
  elif tail -30 "${LOG_DIR}/daily-refresh-cards.log" 2>/dev/null | grep -q '"ok": true'; then
    warn "daily_refresh exited ${SMOKE_RC} but card refresh OK — check institutional tail"
  else
    fail "full smoke failed (rc=${SMOKE_RC}) — see logs/daily-refresh-cards.log"
  fi
fi

echo "=== summary ==="
if [[ ${FAIL} -ne 0 ]]; then
  echo "VERDICT: BLOCKED (${FAIL} hard failure(s))"
  exit 1
fi
if [[ ${WARN} -ne 0 ]]; then
  echo "VERDICT: ARMED WITH WARNINGS — confirm 06:00 UK batch or run --smoke in morning"
  exit 2
fi
echo "VERDICT: ARMED — observation lane ready"
exit 0
