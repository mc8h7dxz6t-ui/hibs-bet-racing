#!/usr/bin/env bash
# Repair football + racing on consolidated VPS (self-contained — no dependency on scripts/ repair bundle).
#
#   sudo bash /opt/hibs-bet/deploy/vps-full-data-repair.sh
set -uo pipefail

BET="${DEPLOY_PATH:-/opt/hibs-bet}"
RACING="${HIBS_RACING_DEPLOY_PATH:-/opt/hibs-racing}"
LOG_DIR="${LOG_DIR:-/var/log/hibs-bet}"
RC=0

step() { echo ""; echo "========== $* =========="; }
warn() { echo "WARN: $*" >&2; }

[[ -d "${BET}/src" ]] || { echo "missing ${BET}" >&2; exit 1; }
[[ "$(id -u)" -eq 0 ]] || { echo "run as root: sudo bash $0" >&2; exit 1; }

PY="${BET}/.venv/bin/python3"
[[ -x "${PY}" ]] || PY="python3"
mkdir -p "${LOG_DIR}" "${BET}/.cache" /var/run/hibs-bet

export HOME="${BET}" DEPLOY_PATH="${BET}" PYTHONPATH="${BET}/src"
export HIBS_CACHE_DIR="${HIBS_CACHE_DIR:-${BET}/.cache}" HIBS_PRODUCTION=1 LOG_DIR="${LOG_DIR}"

touch "${BET}/.env"
grep -q '^HIBS_CACHE_DIR=' "${BET}/.env" 2>/dev/null || echo "HIBS_CACHE_DIR=${BET}/.cache" >>"${BET}/.env"
grep -q '^HIBS_FOOTBALL_DATA_AUTO_SKIP_PAID=' "${BET}/.env" 2>/dev/null || echo 'HIBS_FOOTBALL_DATA_AUTO_SKIP_PAID=1' >>"${BET}/.env"

step "Football — scrape-first profile"
if [[ -f "${BET}/deploy/apply-vps-scrape-first-institutional.sh" ]]; then
  bash "${BET}/deploy/apply-vps-scrape-first-institutional.sh" || RC=1
elif [[ -f "${BET}/deploy/apply-vps-scrape-first.sh" ]]; then
  bash "${BET}/deploy/apply-vps-scrape-first.sh" || RC=1
fi

step "Football — fixture warm"
if [[ -f "${BET}/deploy/vps-warm-and-verify.sh" ]]; then
  bash "${BET}/deploy/vps-warm-and-verify.sh" --warm-only || RC=1
elif [[ -f "${BET}/scripts/vps_fixture_repair.sh" ]]; then
  bash "${BET}/scripts/vps_fixture_repair.sh" || RC=1
elif [[ -f "${BET}/scripts/warm_low_source_scrape.sh" ]]; then
  bash "${BET}/scripts/warm_low_source_scrape.sh" || RC=1
elif [[ -f "${BET}/scripts/warm_football_fixtures.sh" ]]; then
  HIBS_FIXTURE_WARM_FORCE_REFRESH=1 bash "${BET}/scripts/warm_football_fixtures.sh" || RC=1
else
  "${PY}" <<PY || RC=1
import json, os, sys
from pathlib import Path
from dotenv import load_dotenv
load_dotenv("${BET}/.env")
os.environ.setdefault("HIBS_CACHE_DIR", "${BET}/.cache")
sys.path.insert(0, "${BET}/src")
report = {}
try:
    from hibs_predictor.scrapers.robust_scrape_cycle import run_robust_scrape_cycle
    from hibs_predictor.data_aggregator import DataAggregator
    report = run_robust_scrape_cycle(DataAggregator(), force=True)
except ImportError:
    try:
        from hibs_predictor.scrapers.low_source_api import run_low_source_scrape_cycle
        from hibs_predictor.data_aggregator import DataAggregator
        report = run_low_source_scrape_cycle(DataAggregator(), force=True)
    except ImportError:
        from hibs_predictor.web import fetch_all_fixtures
        b = fetch_all_fixtures(force_refresh=True, attach_live=False, allow_stale=True)
        report = {"ok": len(b.get("all") or []) > 0, "fixture_count": len(b.get("all") or [])}
Path("${LOG_DIR}").mkdir(parents=True, exist_ok=True)
Path("${LOG_DIR}/low-source-scrape.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report))
sys.exit(0 if report.get("ok") or int(report.get("fixture_count") or 0) > 0 else 2)
PY
fi

step "Racing — cards"
if [[ ! -d "${RACING}/src" ]]; then
  warn "SKIP racing — ${RACING} missing"
else
  export HIBS_RACING_DEPLOY_PATH="${RACING}" HIBS_BET_DEPLOY_PATH="${BET}"
  if [[ -f "${BET}/scripts/vps_racing_repair.sh" ]]; then
    bash "${BET}/scripts/vps_racing_repair.sh" || RC=1
  elif [[ -f "${BET}/scripts/vps_racing_hard_recovery.sh" ]]; then
    bash "${BET}/scripts/vps_racing_hard_recovery.sh" || RC=1
    if [[ -f "${BET}/deploy/cron-hibs-racing-daily.sh" ]]; then
      bash "${BET}/deploy/cron-hibs-racing-daily.sh" --run >>"${LOG_DIR}/racing-daily.log" 2>&1 || RC=1
    fi
  elif [[ -f "${BET}/deploy/cron-hibs-racing-daily.sh" ]]; then
    bash "${BET}/deploy/cron-hibs-racing-daily.sh" --run >>"${LOG_DIR}/racing-daily.log" 2>&1 || RC=1
  else
    warn "no racing repair script — manual: cd ${RACING} && refresh-cards"
  fi
fi

step "Restart services"
systemctl restart hibs-bet 2>/dev/null || true
systemctl restart hibs-racing 2>/dev/null || true
sleep 4

step "Verify"
curl -sS --max-time 8 http://127.0.0.1:8000/api/ping 2>/dev/null | head -c 200 || warn "football ping failed"
echo ""
curl -sS --max-time 8 http://127.0.0.1:5003/api/ping 2>/dev/null | head -c 200 || warn "racing ping failed"
echo ""
"${PY}" -c "
from hibs_predictor.cache import Cache
from hibs_predictor.web import _all_fixtures_cache_key
p = Cache().peek(_all_fixtures_cache_key())
print('football bundle:', len((p or {}).get('all') or []))
" 2>/dev/null || true

if [[ "${RC}" -eq 0 ]]; then
  echo "========== FULL DATA REPAIR OK =========="
else
  echo "========== REPAIR FINISHED WITH WARNINGS =========="
fi
exit "${RC}"
