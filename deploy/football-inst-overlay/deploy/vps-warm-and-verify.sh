#!/usr/bin/env bash
# All-in-one football verify + fixture warm (works when warm_low_source_scrape.sh is missing).
#
#   sudo bash /opt/hibs-bet/deploy/vps-warm-and-verify.sh
#   sudo bash deploy/vps-warm-and-verify.sh --warm-only
set -uo pipefail

APP="${DEPLOY_PATH:-/opt/hibs-bet}"
LOG_DIR="${LOG_DIR:-/var/log/hibs-bet}"
WARM_ONLY=0
for arg in "$@"; do
  [[ "${arg}" == "--warm-only" ]] && WARM_ONLY=1
done

log() { echo "[vps-warm] $*"; }
warn() { echo "[vps-warm] WARN: $*" >&2; }

[[ -d "${APP}/src" ]] || { warn "missing ${APP}"; exit 1; }
PY="${APP}/.venv/bin/python3"
[[ -x "${PY}" ]] || PY="python3"

export HOME="${APP}" PYTHONPATH="${APP}/src" HIBS_CACHE_DIR="${HIBS_CACHE_DIR:-${APP}/.cache}"
export HIBS_PRODUCTION=1 LOG_DIR="${LOG_DIR}"
mkdir -p "${LOG_DIR}" "${HIBS_CACHE_DIR}" /var/run/hibs-bet

if [[ ${WARM_ONLY} -eq 0 ]]; then
  log "=== ping ==="
  for url in "http://127.0.0.1:8000/api/ping" "http://127.0.0.1:5000/api/ping"; do
    body="$(curl -fsS --max-time 8 "${url}" 2>/dev/null || true)"
    if [[ -n "${body}" ]] && printf '%s' "${body}" | "${PY}" -c "import json,sys; json.load(sys.stdin)" 2>/dev/null; then
      log "OK ${url}"
      printf '%s\n' "${body}" | "${PY}" -m json.tool | head -15
      break
    else
      warn "no JSON from ${url} (body len=${#body})"
    fi
  done

  if systemctl is-active hibs-bet &>/dev/null; then
    log "hibs-bet service: $(systemctl is-active hibs-bet)"
  else
    warn "hibs-bet service not active — start: sudo systemctl start hibs-bet"
  fi

  if [[ -f "${APP}/scripts/measure_dq_7d.py" ]]; then
    log "=== measure_dq_7d ==="
    (cd "${APP}" && "${PY}" scripts/measure_dq_7d.py) || warn "measure_dq_7d failed"
  else
    warn "scripts/measure_dq_7d.py not on this deploy"
  fi
fi

log "=== fixture warm ==="
if [[ -f "${APP}/scripts/warm_low_source_scrape.sh" ]]; then
  bash "${APP}/scripts/warm_low_source_scrape.sh"
elif [[ -f "${APP}/scripts/warm_low_source_scrape.py" ]]; then
  "${PY}" "${APP}/scripts/warm_low_source_scrape.py"
else
  log "warm scripts missing — inline Python warm"
  "${PY}" <<'PY'
import json, os, sys
from pathlib import Path
from dotenv import load_dotenv
load_dotenv("/opt/hibs-bet/.env")
os.environ.setdefault("HOME", "/opt/hibs-bet")
os.environ.setdefault("HIBS_CACHE_DIR", "/opt/hibs-bet/.cache")
sys.path.insert(0, "/opt/hibs-bet/src")

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
        n = len(b.get("all") or [])
        report = {"ok": n > 0, "mode": "fetch_all_fixtures", "fixture_count": n}

log_dir = Path(os.getenv("LOG_DIR", "/var/log/hibs-bet"))
log_dir.mkdir(parents=True, exist_ok=True)
(log_dir / "low-source-scrape.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report))
sys.exit(0 if report.get("ok") or int(report.get("fixture_count") or 0) > 0 else 2)
PY
fi

log "=== bundle check ==="
"${PY}" -c "
from hibs_predictor.cache import Cache
from hibs_predictor.web import _all_fixtures_cache_key, _is_complete_fixture_bundle
peek = Cache().peek(_all_fixtures_cache_key())
n = len((peek or {}).get('all') or []) if isinstance(peek, dict) else 0
print('bundle_count', n, 'complete', _is_complete_fixture_bundle(peek) if isinstance(peek, dict) else False)
"

log "done"
