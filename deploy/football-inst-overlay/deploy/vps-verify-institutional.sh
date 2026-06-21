#!/usr/bin/env bash
# One-shot institutional verification after sync + env apply.
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/hibs-bet}"
cd "${APP_ROOT}"

fail=0
check() {
  if "$@"; then
    echo "OK  $*"
  else
    echo "FAIL $*"
    fail=1
  fi
}

echo "==> revision"
test -f .deploy-revision && cat .deploy-revision || { echo "MISSING .deploy-revision"; fail=1; }

echo "==> required modules"
PYTHONPATH=src .venv/bin/python -c "
from hibs_predictor.audit_settlement_resolvers import resolve_ft_from_scrape_fallback
from hibs_predictor.scrapers.settlement_ft_backups import resolve_ft_from_espn_scoreboard
print('settlement modules OK')
" || fail=1

echo "==> env flags"
grep -q 'HIBS_DISABLE_API_SPORTS=1' .env 2>/dev/null && echo "OK  API off" || echo "WARN API-Sports not disabled"
grep -q 'HIBS_MAX_DATA=1' .env 2>/dev/null && echo "OK  MAX_DATA" || echo "WARN HIBS_MAX_DATA not 1 (DQ may differ from institutional)"
grep -q 'HIBS_SETTLE_BACKUP_ESPN=1' .env 2>/dev/null && echo "OK  ESPN settlement backup" || echo "WARN ESPN backup off"

echo "==> service"
systemctl is-active hibs-bet.service

echo "==> ping"
curl -fsS --max-time 10 http://127.0.0.1:8000/api/ping | head -c 500
echo ""

exit "${fail}"
