#!/usr/bin/env bash
# Matchbook API credential helpers (hibs-racing .env).
# shellcheck disable=SC2034

matchbook_load_env() {
  local env_file="${1:-}"
  [[ -n "${env_file}" && -f "${env_file}" ]] || return 0
  local line k v
  while IFS= read -r line || [[ -n "${line}" ]]; do
    line="${line%%#*}"
    line="${line#"${line%%[![:space:]]*}"}"
    [[ "${line}" == MATCHBOOK_*=* ]] || continue
    k="${line%%=*}"
    v="${line#*=}"
    v="${v%\"}"
    v="${v#\"}"
    v="${v%\'}"
    v="${v#\'}"
    export "${k}=${v}"
  done < <(grep -E '^MATCHBOOK_' "${env_file}" 2>/dev/null || true)
  matchbook_normalize_env
}

matchbook_normalize_env() {
  if [[ -z "${MATCHBOOK_USER:-}" && -n "${MATCHBOOK_USERNAME:-}" ]]; then
    export MATCHBOOK_USER="${MATCHBOOK_USERNAME}"
  fi
  if [[ -z "${MATCHBOOK_USERNAME:-}" && -n "${MATCHBOOK_USER:-}" ]]; then
    export MATCHBOOK_USERNAME="${MATCHBOOK_USER}"
  fi
}

matchbook_credentials_ok() {
  matchbook_normalize_env
  [[ -n "${MATCHBOOK_USER:-}${MATCHBOOK_USERNAME:-}" && -n "${MATCHBOOK_PASSWORD:-}" ]]
}

matchbook_user_value() {
  matchbook_normalize_env
  echo "${MATCHBOOK_USER:-${MATCHBOOK_USERNAME:-}}"
}

matchbook_env_lines() {
  local env_file="${1:-}"
  matchbook_load_env "${env_file}"
  if ! matchbook_credentials_ok; then
    return 1
  fi
  local user
  user="$(matchbook_user_value)"
  printf 'MATCHBOOK_USER=%s\nMATCHBOOK_PASSWORD=%s\n' "${user}" "${MATCHBOOK_PASSWORD}"
}

# Session login probe — sets MATCHBOOK_SESSION_JSON / MATCHBOOK_SESSION_TOKEN on success.
matchbook_session_probe() {
  matchbook_normalize_env
  if ! matchbook_credentials_ok; then
    return 1
  fi
  local user pass body
  user="$(matchbook_user_value)"
  pass="${MATCHBOOK_PASSWORD}"
  body="$(curl -sS --max-time 25 -X POST 'https://api.matchbook.com/bpapi/rest/security/session' \
    -H 'Content-Type: application/json' \
    -H 'Accept: application/json' \
    -d "$(python3 -c 'import json,sys; print(json.dumps({"username":sys.argv[1],"password":sys.argv[2]}))' "${user}" "${pass}")")"
  export MATCHBOOK_SESSION_JSON="${body}"
  MATCHBOOK_SESSION_TOKEN="$(printf '%s' "${body}" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    print(d.get('session-token') or '')
except Exception:
    print('')
" 2>/dev/null || true)"
  export MATCHBOOK_SESSION_TOKEN
  [[ -n "${MATCHBOOK_SESSION_TOKEN}" ]]
}

matchbook_session_balance() {
  local json="${MATCHBOOK_SESSION_JSON:-}"
  [[ -n "${json}" ]] || return 1
  printf '%s' "${json}" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    bal = d.get('account', {}).get('balance')
    print('' if bal is None else bal)
except Exception:
    print('')
"
}

# Matchbook grants API access after ~\$200 funded (see hibs-racing docs/MATCHBOOK_API_REQUEST.md).
matchbook_funded_ok() {
  local min_usd="${1:-${MATCHBOOK_MIN_FUNDED_USD:-200}}"
  local bal
  bal="$(matchbook_session_balance)"
  [[ -n "${bal}" ]] || return 1
  python3 -c 'import sys; bal=float(sys.argv[1]); need=float(sys.argv[2]); sys.exit(0 if bal >= need else 1)' \
    "${bal}" "${min_usd}"
}
