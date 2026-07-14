#!/usr/bin/env bash
# Post-observation Matchbook readiness — racing odds lane + FVE arb ladder (read-only audit).
#
# Run on Mac after observation period (formal gate ~2026-06-19) before funding / micro-live.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RACING_REPO="$(bash "${REPO_ROOT}/scripts/resolve_hibs_racing_repo.sh" 2>/dev/null || echo "${HOME}/hibs-racing")"
FVE_REPO="${FVE_REPO:-${HOME}/football-app}"
FAIL=0
WARN=0

pass() { echo "PASS: $*"; }
fail() { echo "FAIL: $*" >&2; FAIL=1; }
warn() { echo "WARN: $*" >&2; WARN=1; }

echo "=== Matchbook post-observation readiness ==="
echo "utc: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "hibs-bet: ${REPO_ROOT}"
echo "racing:   ${RACING_REPO}"
echo "fve:      ${FVE_REPO}"
echo ""

echo "--- 1/4 funded account + API session ---"
if bash "${REPO_ROOT}/scripts/preflight_matchbook_funded.sh" "${RACING_REPO}/.env" --probe-edge; then
  :
else
  rc=$?
  if [[ ${rc} -eq 0 ]]; then
    :
  else
    fail "matchbook funded preflight blocked (exit ${rc})"
  fi
fi

echo ""
echo "--- 2/4 racing — exit observation lane ---"
if [[ -x "${RACING_REPO}/scripts/preflight_matchbook_post_observation.sh" ]]; then
  set +e
  bash "${RACING_REPO}/scripts/preflight_matchbook_post_observation.sh"
  RACING_RC=$?
  set -e
  if [[ ${RACING_RC} -eq 0 ]]; then
    pass "racing post-observation preflight"
  elif [[ ${RACING_RC} -eq 2 ]]; then
    warn "racing post-observation preflight — armed with warnings"
  else
    fail "racing post-observation preflight blocked"
  fi
else
  warn "missing ${RACING_REPO}/scripts/preflight_matchbook_post_observation.sh — pull hibs-bet-racing"
fi

echo ""
echo "--- 3/4 FVE — arb ladder stage audit ---"
if [[ -x "${FVE_REPO}/scripts/preflight_matchbook_arb_stage.sh" ]]; then
  set +e
  bash "${FVE_REPO}/scripts/preflight_matchbook_arb_stage.sh"
  FVE_RC=$?
  set -e
  if [[ ${FVE_RC} -eq 0 ]]; then
    pass "FVE arb stage audit"
  else
    warn "FVE arb not ready for micro-live — see football-app/docs/ARB_FREEZE.md"
  fi
else
  warn "missing ${FVE_REPO}/scripts/preflight_matchbook_arb_stage.sh — pull football-app"
fi

echo ""
echo "--- 4/4 VPS credential sync (dry-run instructions) ---"
if [[ -f "${REPO_ROOT}/deploy/apply-vps-matchbook-env-sync.sh" ]]; then
  pass "VPS sync script present — run on main VPS as root after local GREEN"
  echo "    sudo bash ${REPO_ROOT}/deploy/apply-vps-matchbook-env-sync.sh"
else
  warn "deploy/apply-vps-matchbook-env-sync.sh not found"
fi

echo ""
echo "=== summary ==="
if [[ ${FAIL} -ne 0 ]]; then
  echo "VERDICT: BLOCKED — fix hard failures before funding / go-live"
  exit 1
fi
if [[ ${WARN} -ne 0 ]]; then
  echo "VERDICT: PARTIAL — fund Matchbook, then complete FVE shadow soak before micro-live"
  exit 2
fi
echo "VERDICT: GREEN — fund account, sync VPS creds, advance arb ladder per runbook"
exit 0
