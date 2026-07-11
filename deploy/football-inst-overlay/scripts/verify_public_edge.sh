#!/usr/bin/env bash
# Public edge smoke — separate curls per URL (never one -w for multiple URLs).
#
#   bash /opt/hibs-bet/scripts/verify_public_edge.sh
#   HIBS_PUBLIC_HOST=www.hibs-bet.co.uk bash ...
set -euo pipefail

APP="${DEPLOY_PATH:-/opt/hibs-bet}"
PUBLIC="${HIBS_PUBLIC_HOST:-hibs-bet.co.uk}"
FVE_HOST="${FVE_REMOTE_HOST:-127.0.0.1}"
FVE_PORT="${FVE_API_PORT:-8010}"
fail=0

if [[ -f /etc/hibs-bet/stack.env ]]; then
  # shellcheck disable=SC1091
  source /etc/hibs-bet/stack.env
  PUBLIC="${HIBS_PUBLIC_HOST:-${PUBLIC}}"
  FVE_HOST="${FVE_REMOTE_HOST:-${FVE_HOST}}"
fi

probe() {
  local label="$1" url="$2" expect="${3:-200}"
  local code
  code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 15 "${url}" 2>/dev/null || echo 000)"
  if [[ "${expect}" == *"|"* ]]; then
    if [[ "${code}" =~ ^(${expect})$ ]]; then
      echo "OK   ${label} ${code} ${url}"
    else
      echo "FAIL ${label} ${code} (want ${expect}) ${url}" >&2
      fail=1
    fi
  elif [[ "${code}" == "${expect}" ]]; then
    echo "OK   ${label} ${code} ${url}"
  else
    echo "FAIL ${label} ${code} (want ${expect}) ${url}" >&2
    fail=1
  fi
}

echo "==> verify_public_edge host=${PUBLIC}"

probe "local_football_ping" "http://127.0.0.1:8000/api/ping" "200"
probe "local_football_root" "http://127.0.0.1:8000/" "200|302"
probe "local_football_login" "http://127.0.0.1:8000/login" "200|302"
probe "local_racing_ping" "http://127.0.0.1:5003/api/ping" "200"

probe "public_football_login" "https://${PUBLIC}/login" "200|302"
probe "public_football_root" "https://${PUBLIC}/" "200|302"
probe "public_racing_ping" "https://${PUBLIC}/racing/api/ping" "200"

if curl -fsS --max-time 8 "http://${FVE_HOST}:${FVE_PORT}/health" >/dev/null 2>&1; then
  echo "OK   fve_upstream_health http://${FVE_HOST}:${FVE_PORT}/health"
  probe "public_fve_api" "https://${PUBLIC}/fve-api/health" "200"
else
  echo "WARN fve_upstream_health http://${FVE_HOST}:${FVE_PORT}/health unreachable"
fi

probe "public_line_trader" "https://${PUBLIC}/line-trader" "200|302"

if [[ -f "${APP}/templates/_product_switcher.html" ]]; then
  echo "OK   ui_product_switcher ${APP}/templates/_product_switcher.html"
else
  echo "FAIL ui_product_switcher missing overlay template" >&2
  fail=1
fi

exit "${fail}"
