#!/usr/bin/env bash
# Racing institutional readiness gate — health, data producer SLO, paper ledger.
#
#   bash scripts/verify_racing_institutional_readiness.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${ROOT}/.venv/bin/python3"
[[ -x "${PY}" ]] || PY="python3"
export PYTHONPATH="${ROOT}/src"

fail=0
step() { echo ""; echo "==> $*"; }

step "data producer SLO"
"${PY}" -c "
from hibs_racing.data_producer_slo import build_data_producer_snapshot
import json, sys
snap = build_data_producer_snapshot()
print(json.dumps(snap.get('producers', {}), indent=2))
sys.exit(0 if snap.get('ok') else 1)
" || fail=1

step "health full (local)"
"${PY}" -c "
from hibs_racing.web_service import health_status
h = health_status().to_dict()
print('card_fresh', h.get('card_fresh'), 'nan_ok', h.get('nan_integrity_passed'))
dp = h.get('data_producer') or {}
print('data_producer_ok', dp.get('ok'))
import sys
sys.exit(0 if h.get('db_ok') and dp.get('ok') is not False else 1)
" || fail=1

step "paper ledger rows"
"${PY}" -c "
from hibs_racing.place.paper_ledger import load_ledger_rows, ledger_stats
rows = load_ledger_rows(limit=5, backtest=False)
stats = ledger_stats(backtest=False)
print('ledger_rows', len(rows), 'settled', stats.settled_bets, 'open', stats.open_bets)
"

if [[ ${fail} -ne 0 ]]; then
  echo ""
  echo "FAIL: racing institutional readiness not green"
  exit 1
fi

echo ""
echo "PASS: racing institutional readiness"
