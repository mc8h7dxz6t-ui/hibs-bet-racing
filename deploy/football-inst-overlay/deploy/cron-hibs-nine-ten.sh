#!/usr/bin/env bash
# Nine-ten pillar scorecard — daily engineering + evidence snapshot.
#
#   sudo bash /opt/hibs-bet/deploy/cron-hibs-nine-ten.sh --install
#   sudo bash /opt/hibs-bet/deploy/cron-hibs-nine-ten.sh --run
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/hibs-bet}"
LOG_DIR="${LOG_DIR:-/var/log/hibs-bet}"
LOG_FILE="${LOG_DIR}/nine-ten-score.log"
STATUS_JSON="${LOG_DIR}/institutional-status.json"
MARKER="# hibs-bet: nine-ten daily"
SCORE="${APP_ROOT}/scripts/score_hibs_nine_ten.sh"
PY="${APP_ROOT}/.venv/bin/python3"
[[ -x "${PY}" ]] || PY="python3"

usage() {
  echo "Usage: $0 [--print|--install|--run]"
}

run_score() {
  mkdir -p "${LOG_DIR}"
  {
    echo "===== $(date -u +%Y-%m-%dT%H:%M:%SZ) nine-ten score ====="
    cd "${APP_ROOT}"
    HOME="${APP_ROOT}" PYTHONPATH=src bash "${SCORE}"
    HOME="${APP_ROOT}" PYTHONPATH=src "${PY}" -c "
from hibs_predictor.institutional_failsafe import failsafe_report
import json
print(json.dumps(failsafe_report(app_root='${APP_ROOT}'), indent=2, default=str))
" > "${STATUS_JSON}"
    echo "===== done ====="
  } >>"${LOG_FILE}" 2>&1
  chown www-data:www-data "${LOG_FILE}" "${STATUS_JSON}" 2>/dev/null || true
}

install_cron() {
  mkdir -p "${LOG_DIR}"
  chmod +x "${SCORE}" 2>/dev/null || true
  local existing tmp
  existing="$(crontab -u www-data -l 2>/dev/null || true)"
  existing="$(printf '%s\n' "${existing}" | grep -vF "${MARKER}" | grep -vF 'score_hibs_nine_ten.sh' || true)"
  tmp="$(mktemp)"
  {
    printf '%s\n' "${existing}"
    echo ""
    echo "${MARKER}"
    echo "15 7 * * * cd ${APP_ROOT} && HOME=${APP_ROOT} bash ${APP_ROOT}/deploy/cron-hibs-nine-ten.sh --run >> ${LOG_FILE} 2>&1"
  } >"${tmp}"
  crontab -u www-data "${tmp}"
  rm -f "${tmp}"
  echo "Installed nine-ten score -> ${LOG_FILE}"
}

case "${1:---print}" in
  --install) install_cron ;;
  --run) run_score ;;
  --print)
    echo "${MARKER}"
    echo "15 7 * * * cd ${APP_ROOT} && HOME=${APP_ROOT} bash ${APP_ROOT}/deploy/cron-hibs-nine-ten.sh --run >> ${LOG_FILE} 2>&1"
    ;;
  -h|--help) usage ;;
  *) usage; exit 1 ;;
esac
