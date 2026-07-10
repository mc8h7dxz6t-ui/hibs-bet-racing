#!/usr/bin/env bash
# Verify racing .env credentials are set and live sources respond (no secrets printed).
#
#   cd /opt/hibs-racing && bash scripts/verify_racing_creds.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
source "${ROOT}/scripts/_lib.sh" 2>/dev/null || true

if [[ -f "${ROOT}/.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${ROOT}/.env"
  set +a
fi

PY="${ROOT}/.venv/bin/python3"
[[ -x "${PY}" ]] || PY="python3"
export PYTHONPATH="${ROOT}/src"

ok=0
warn=0
fail=0

_check() {
  local name="$1"
  local val="$2"
  if [[ -n "${val}" ]]; then
    echo "  OK   ${name} set"
    ok=$((ok + 1))
  else
    echo "  MISS ${name}"
    fail=$((fail + 1))
  fi
}

echo "==> env presence"
_check "RACING_API_USERNAME" "${RACING_API_USERNAME:-}"
_check "RACING_API_PASSWORD" "${RACING_API_PASSWORD:-}"
_check "MATCHBOOK_USERNAME" "${MATCHBOOK_USERNAME:-${MATCHBOOK_USER:-}}"
_check "MATCHBOOK_PASSWORD" "${MATCHBOOK_PASSWORD:-}"
_check "HIBS_ODDS_SOURCE" "${HIBS_ODDS_SOURCE:-auto}"
_check "HIBS_RACING_CARD_SOURCE" "${HIBS_RACING_CARD_SOURCE:-auto}"

if [[ -n "${EMAIL:-}" && -n "${ACCESS_TOKEN:-}" ]]; then
  echo "  OK   Racing Post scrape (EMAIL + ACCESS_TOKEN)"
  ok=$((ok + 1))
else
  echo "  SKIP Racing Post scrape (optional enrich)"
  warn=$((warn + 1))
fi

echo ""
echo "==> scrape / guard status"
"${PY}" -c "
import json
from hibs_racing.scrapers.racing_scrape_api import scrape_status_payload
print(json.dumps(scrape_status_payload(), indent=2))
"

echo ""
echo "==> matchbook dry-run"
set +e
"${PY}" -m hibs_racing.cli dry-run-quotes 2>&1 | head -20
mb_rc=$?
set -e
if [[ ${mb_rc} -eq 0 ]]; then
  echo "  OK   Matchbook quotes reachable"
  ok=$((ok + 1))
else
  echo "  WARN Matchbook dry-run failed (rc=${mb_rc}) — check creds or HIBS_MATCHBOOK_VPS_OVERRIDE=1"
  warn=$((warn + 1))
fi

echo ""
echo "==> odds coverage (current DB)"
"${PY}" -c "
import json
from hibs_racing.scrapers.racing_scrape_api import odds_coverage_summary
cov = odds_coverage_summary()
print(json.dumps(cov, indent=2))
import sys
sys.exit(0 if cov.get('ok') else 2)
" && ok=$((ok + 1)) || warn=$((warn + 1))

echo ""
echo "Summary: ok=${ok} warn=${warn} miss=${fail}"
if [[ ${fail} -gt 0 ]]; then
  echo "FAIL: required credentials missing"
  exit 1
fi
if [[ ${warn} -gt 0 ]]; then
  echo "WARN: partial — run daily_refresh after fixing issues"
  exit 2
fi
echo "PASS: racing credentials look good"
