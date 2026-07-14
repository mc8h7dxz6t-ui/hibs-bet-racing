#!/usr/bin/env bash
# Local pre-flight for HIBS platforms — read-only probes, no trading submits.
# Usage: ./scripts/three_platform_prime_check.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
export PYTHONPATH="${REPO_ROOT}/src${PYTHONPATH:+:$PYTHONPATH}"

step() { echo ""; echo "==> $*"; }
warn() { echo "WARN: $*" >&2; }

step "Football institutional + scraper catalog"
python3 -m hibs_predictor.main institutional-check --json >/dev/null || warn "institutional-check issues"
python3 -c "from hibs_predictor.scrapers.multi_scraper_api import catalog_summary; c=catalog_summary(); assert 'ft_result' in c['field_ladders']"

step "FVE upstream lines proxy (in-process)"
python3 -c "from hibs_predictor.fve_lines_proxy import build_lines_payload; p=build_lines_payload(lambda:{'all':[{'home_team':'A','away_team':'B','best_odds_1x2':{}}]}, 'A v B'); assert p['ok']"

step "FVE / line-trader probe (optional remote)"
FVE_URL="${FVE_API_URL:-http://127.0.0.1:8010}"
if curl -fsS --max-time 3 "${FVE_URL}/health" >/dev/null 2>&1; then
  echo "FVE health OK at ${FVE_URL}"
  curl -fsS --max-time 3 "${FVE_URL}/health" | python3 -c "import sys,json; d=json.load(sys.stdin); print('  paused=', d.get('paused'), 'worker=', (d.get('worker') or {}).get('alive'))"
else
  warn "FVE not reachable at ${FVE_URL} — run deploy/apply-vps-fve-line-trader.sh on VPS"
fi

if curl -fsS --max-time 3 "http://127.0.0.1:8000/api/fve/status" >/dev/null 2>&1; then
  echo "hibs /api/fve/status OK"
else
  warn "hibs FVE status endpoint not reachable (local gunicorn may be down)"
fi

step "Trading paper link (local / VPS probe when configured)"
if [[ -x "${REPO_ROOT}/scripts/verify_trading_link.sh" ]]; then
  bash "${REPO_ROOT}/scripts/verify_trading_link.sh" || warn "trading link not ready — run link_paper_trading.sh before go-live"
else
  warn "verify_trading_link.sh missing"
fi

step "Racing sibling repo (optional)"
RACING_ROOT="${HIBS_RACING_REPO:-$(dirname "$REPO_ROOT")/hibs-bet-racing}"
if [[ -d "${RACING_ROOT}/src/hibs_racing" ]]; then
  PYTHONPATH="${RACING_ROOT}/src" python3 -c "
from hibs_racing.scrapers.multi_scraper_api import catalog_summary
c = catalog_summary()
assert c['product'] == 'hibs-racing'
assert 'win_odds' in c['field_ladders']
print('racing catalog OK')
"
else
  warn "hibs-bet-racing not found at ${RACING_ROOT}"
fi

FVE_ROOT="${FVE_DEPLOY_PATH:-$(dirname "$REPO_ROOT")/football-app}"
if [[ -f "${FVE_ROOT}/api/main.py" ]]; then
  step "FVE repo present — preflight"
  if [[ -x "${FVE_ROOT}/scripts/preflight_fve.sh" ]]; then
    FVE_API_URL="${FVE_URL}" bash "${FVE_ROOT}/scripts/preflight_fve.sh" || warn "FVE preflight issues"
  fi
else
  warn "football-app (FVE) not found at ${FVE_ROOT}"
fi

echo ""
echo "Platform prime check complete (no performance-impacting writes)."
