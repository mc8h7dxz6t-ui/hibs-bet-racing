#!/usr/bin/env bash
# Test Matchbook exchange login (same creds as matchbook.com website — NOT Racing API).
#
#   ./scripts/test_matchbook_credentials.sh ~/hibs-racing/.env
#   MATCHBOOK_USER=you MATCHBOOK_PASSWORD=secret ./scripts/test_matchbook_credentials.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RACING_REPO="$(bash "${REPO_ROOT}/scripts/resolve_hibs_racing_repo.sh" 2>/dev/null || echo "${HOME}/hibs-racing")"
ENV_FILE="${1:-${RACING_REPO}/.env}"

# shellcheck source=lib_matchbook_env.sh
source "${REPO_ROOT}/scripts/lib_matchbook_env.sh"

fail() { echo "FAIL: $*" >&2; exit 1; }
warn() { echo "WARN: $*" >&2; }

echo "==> Matchbook credential test"
echo "    env: ${ENV_FILE}"
echo "    (website login — NOT theracingapi.com RACING_API_*)"
echo ""

matchbook_load_env "${ENV_FILE}"

if ! matchbook_credentials_ok; then
  fail "set MATCHBOOK_USER and MATCHBOOK_PASSWORD in ${ENV_FILE}

hibs-racing expects:
  MATCHBOOK_USER=your_matchbook_username
  MATCHBOOK_PASSWORD=your_matchbook_password

Common mistakes:
  • RACING_API_USERNAME is theracingapi.com — different product
  • email vs username — use the same handle you type at matchbook.com login
  • password with ! or # must be quoted: MATCHBOOK_PASSWORD='your pass'"
fi

USER="$(matchbook_user_value)"
PASS="${MATCHBOOK_PASSWORD}"

echo "==> Login probe (bpapi)"
body="$(curl -sS --max-time 25 -X POST 'https://api.matchbook.com/bpapi/rest/security/session' \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  -d "$(python3 -c 'import json,sys; print(json.dumps({"username":sys.argv[1],"password":sys.argv[2]}))' "${USER}" "${PASS}")")"

if echo "${body}" | grep -q 'session-token'; then
  bal="$(echo "${body}" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('account',{}).get('balance','?'))" 2>/dev/null || echo '?')"
  echo "GREEN: Matchbook login OK (balance=${bal} — zero balance is fine for odds reads)"
  echo ""
  echo "Next:"
  echo "  bash ${REPO_ROOT}/scripts/preflight_matchbook_funded.sh ${ENV_FILE} --require-funded"
  echo "  bash ${REPO_ROOT}/scripts/matchbook_post_observation_readiness.sh"
  echo ""
  echo "Note: matchbook:false in /api/health does not always mean no odds —"
  echo "      unscored_runners and nan_integrity_passed are the value-lane blockers."
  exit 0
fi

if echo "${body}" | grep -qi 'incorrect'; then
  fail "username or password rejected by Matchbook

Try on https://www.matchbook.com in a browser with the SAME values.
If browser works but API fails, contact api@matchbook.com (API access flag).
If browser also fails: reset password, then update ${ENV_FILE} and VPS .env"
fi

if echo "${body}" | grep -qi 'LOGIN_LOCATION_RESTRICTED\|location'; then
  fail "Matchbook blocked login from this IP (location restriction).
Run this test from your Mac (UK), not a datacenter VPN."
fi

if echo "${body}" | grep -qi 'gambling is restricted'; then
  fail "Matchbook account restricted (gambling/location). Check account status after withdrawal."
fi

warn "unexpected response:"
echo "${body}" | head -c 400
echo ""
fail "Matchbook login did not return session-token — see response above"
