#!/usr/bin/env bash
# Post-observation racing gate — exit HIBS_OBSERVATION_LANE=1 before production thresholds.
# Exit 0 = GO · 2 = armed with warnings · 1 = blocked.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/_lib.sh"

HIBS_BET_ROOT="${HIBS_BET_ROOT:-$(cd "${SCRIPT_DIR}/../.." 2>/dev/null && pwd)}"
if [[ ! -f "${HIBS_BET_ROOT}/scripts/lib_matchbook_env.sh" ]]; then
  HIBS_BET_ROOT="${HOME}/hibs-bet"
fi

FAIL=0
WARN=0
pass() { echo "PASS: $*"; }
fail() { echo "FAIL: $*" >&2; FAIL=1; }
warn() { echo "WARN: $*" >&2; WARN=1; }

activate_venv
load_env

echo "=== racing post-observation Matchbook gate ==="
echo "repo: ${ROOT}"
echo "utc:  $(date -u +%Y-%m-%dT%H:%M:%SZ)"

obs="${HIBS_OBSERVATION_LANE:-1}"
if [[ "${obs}" == "1" || "${obs}" == "true" || "${obs}" == "yes" ]]; then
  warn "HIBS_OBSERVATION_LANE still 1 — set HIBS_OBSERVATION_LANE=0 in .env after formal gate"
else
  pass "HIBS_OBSERVATION_LANE=0 (production thresholds)"
fi

if [[ -f "${HIBS_BET_ROOT}/scripts/preflight_matchbook_funded.sh" ]]; then
  set +e
  bash "${HIBS_BET_ROOT}/scripts/preflight_matchbook_funded.sh" "${ROOT}/.env" --require-funded --probe-edge
  MB_RC=$?
  set -e
  if [[ ${MB_RC} -eq 0 ]]; then
    pass "Matchbook funded + API session"
  else
    fail "Matchbook funded preflight (exit ${MB_RC})"
  fi
else
  warn "hibs-bet preflight_matchbook_funded.sh not found at ${HIBS_BET_ROOT}"
fi

echo "--- institutional-check (production, no --observation-lane) ---"
set +e
INST_JSON="$(hibs-racing institutional-check --days 14 --card-date "$(date -u +%F)" 2>/dev/null)"
INST_RC=$?
set -e
RECON_CLEAN="$(printf '%s' "${INST_JSON}" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(d.get('paper_reconciliation', {}).get('is_clean', False))
except Exception:
    print(False)
" 2>/dev/null || echo False)"
SETTLED="$(printf '%s' "${INST_JSON}" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    pl = d.get('paper_ledger') or {}
    print(pl.get('settled_rows', pl.get('settled', 0)) or 0)
except Exception:
    print(0)
" 2>/dev/null || echo 0)"

if [[ ${INST_RC} -eq 0 ]]; then
  pass "institutional-check passed (production)"
elif [[ "${RECON_CLEAN}" == "True" && "${SETTLED}" -gt 0 ]]; then
  pass "institutional-check: recon clean, settled_rows=${SETTLED}"
else
  fail "institutional-check blocked — recon=${RECON_CLEAN} settled_rows=${SETTLED}"
fi

TB_PASS="$(printf '%s' "${INST_JSON}" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(d.get('telemetry_balance', {}).get('passed', False))
except Exception:
    print(False)
" 2>/dev/null || echo False)"
if [[ "${TB_PASS}" == "True" ]]; then
  pass "telemetry balance (prod ≥50% Matchbook coverage)"
else
  warn "telemetry balance below prod bar — run refresh-cards after 06:00 UK"
fi

if python3 -c "from hibs_racing.live.execution_config import execution_disabled; import sys; sys.exit(0 if execution_disabled() else 1)" 2>/dev/null; then
  pass "live execution disabled (analytics-only — expected)"
else
  warn "execution_disabled() is False — verify before any sale / compliance review"
fi

echo "=== summary ==="
if [[ ${FAIL} -ne 0 ]]; then
  echo "VERDICT: BLOCKED"
  exit 1
fi
if [[ ${WARN} -ne 0 ]]; then
  echo "VERDICT: ARMED WITH WARNINGS"
  exit 2
fi
echo "VERDICT: GREEN — racing Matchbook odds lane ready (paper only)"
exit 0
