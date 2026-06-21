#!/usr/bin/env bash
# Pre-flight: Matchbook funded account + API session (post-observation gate).
#
#   ./scripts/preflight_matchbook_funded.sh ~/hibs-racing/.env
#   ./scripts/preflight_matchbook_funded.sh --require-funded
#   MATCHBOOK_MIN_FUNDED_USD=200 ./scripts/preflight_matchbook_funded.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RACING_REPO="$(bash "${REPO_ROOT}/scripts/resolve_hibs_racing_repo.sh" 2>/dev/null || echo "${HOME}/hibs-racing")"
ENV_FILE="${RACING_REPO}/.env"
REQUIRE_FUNDED=0
PROBE_EDGE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --require-funded) REQUIRE_FUNDED=1 ;;
    --probe-edge) PROBE_EDGE=1 ;;
    -h|--help)
      echo "Usage: $0 [env_file] [--require-funded] [--probe-edge]"
      echo "  --require-funded  Fail unless balance >= MATCHBOOK_MIN_FUNDED_USD (default 200)"
      echo "  --probe-edge      Hit edge/rest with session token (racing odds path)"
      exit 0
      ;;
    *)
      ENV_FILE="$1"
      ;;
  esac
  shift
done

# shellcheck source=lib_matchbook_env.sh
source "${REPO_ROOT}/scripts/lib_matchbook_env.sh"

fail() { echo "FAIL: $*" >&2; exit 1; }
pass() { echo "PASS: $*"; }
warn() { echo "WARN: $*" >&2; }

echo "=== Matchbook funded pre-flight ==="
echo "env: ${ENV_FILE}"
echo "utc: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo ""

matchbook_load_env "${ENV_FILE}"
if ! matchbook_credentials_ok; then
  fail "set MATCHBOOK_USER and MATCHBOOK_PASSWORD in ${ENV_FILE}"
fi
pass "credentials present"

if ! matchbook_session_probe; then
  body="${MATCHBOOK_SESSION_JSON:-}"
  if echo "${body}" | grep -qi 'incorrect'; then
    fail "username or password rejected — verify at https://www.matchbook.com"
  fi
  if echo "${body}" | grep -qi 'LOGIN_LOCATION_RESTRICTED\|location'; then
    fail "location restricted — run from UK IP, not datacenter VPN"
  fi
  if echo "${body}" | grep -qi 'gambling is restricted'; then
    fail "account restricted — check Matchbook account status"
  fi
  fail "no session-token — fund account (\$200 min) and confirm API access with api@matchbook.com"
fi
pass "session login OK"

bal="$(matchbook_session_balance)"
min_usd="${MATCHBOOK_MIN_FUNDED_USD:-200}"
if [[ -n "${bal}" ]]; then
  echo "balance: ${bal} (min funded gate: \$${min_usd})"
  if matchbook_funded_ok "${min_usd}"; then
    pass "balance meets funded threshold"
  elif [[ ${REQUIRE_FUNDED} -eq 1 ]]; then
    fail "balance ${bal} below \$${min_usd} — deposit before API access / post-obs go-live"
  else
    warn "balance below \$${min_usd} — fund before Matchbook grants API access"
  fi
else
  warn "could not parse balance from session response"
fi

if [[ ${PROBE_EDGE} -eq 1 ]]; then
  echo "--- edge/rest probe (racing odds path) ---"
  edge_code="$(curl -sS -o /tmp/mb_edge_probe.json -w '%{http_code}' --max-time 20 \
    -H "session-token: ${MATCHBOOK_SESSION_TOKEN}" \
    -H 'Accept: application/json' \
    'https://api.matchbook.com/edge/rest/events?per-page=1&sport-ids=9' || echo 000)"
  if [[ "${edge_code}" == "200" ]]; then
    pass "edge/rest reachable (horse racing sport id)"
  else
    warn "edge/rest returned HTTP ${edge_code} — API flag may still be pending after funding"
    head -c 200 /tmp/mb_edge_probe.json 2>/dev/null || true
    echo ""
  fi
fi

echo ""
echo "VERDICT: READY FOR POST-OBS MATCHBOOK (credentials + session)"
echo "Next:"
echo "  bash ${REPO_ROOT}/scripts/matchbook_post_observation_readiness.sh"
echo "  sudo bash ${REPO_ROOT}/deploy/apply-vps-matchbook-env-sync.sh  # VPS creds sync"
