#!/usr/bin/env bash
# Racing robust scrape cycle — cards + odds + thin rescue (Inst++).
#
#   bash /opt/hibs-racing/scripts/warm_racing_scrape.sh
set -euo pipefail

APP="${HIBS_RACING_DEPLOY_PATH:-/opt/hibs-racing}"
LOG_DIR="${LOG_DIR:-/var/log/hibs-racing}"
LOCK="/var/run/hibs-racing/robust-scrape.lock"

mkdir -p "${LOG_DIR}" /var/run/hibs-racing
cd "${APP}"

if [[ ! -x "${APP}/.venv/bin/python3" ]]; then
  echo "[racing-scrape] ERROR: missing ${APP}/.venv/bin/python3" >&2
  exit 1
fi

exec 9>"${LOCK}"
if ! flock -n 9; then
  echo "[racing-scrape] skip — another cycle in progress"
  exit 0
fi

export HOME="${APP}"
export PYTHONPATH="${APP}/src"
export LOG_DIR="${LOG_DIR}"
export HIBS_RACING_CACHE_DIR="${HIBS_RACING_CACHE_DIR:-${APP}/data/.cache}"
export HIBS_ALWAYS_SCRAPE="${HIBS_ALWAYS_SCRAPE:-1}"
export HIBS_RACING_SCRAPE_FORCE="${HIBS_RACING_SCRAPE_FORCE:-${HIBS_ALWAYS_SCRAPE:-1}}"
export PIP_CACHE_DIR="${PIP_CACHE_DIR:-${APP}/.cache/pip}"
mkdir -p "${PIP_CACHE_DIR}" "${HIBS_RACING_CACHE_DIR}"

# Honour scrape-first flags from .env (root shell exports are ignored by sudo -u www-data).
if [[ -f "${APP}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${APP}/.env"
  set +a
fi
export HIBS_RACING_SCRAPE_FIRST="${HIBS_RACING_SCRAPE_FIRST:-0}"
export HIBS_RACING_SCRAPE_SOURCE="${HIBS_RACING_SCRAPE_SOURCE:-auto}"

PY="${APP}/.venv/bin/python3"
SCRAPE_PY="${APP}/scripts/warm_racing_scrape.py"

if [[ "$(id -u)" -eq 0 ]] && id www-data &>/dev/null; then
  chown -R www-data:www-data "${APP}/.cache" 2>/dev/null || true
  sudo -u www-data env \
    HOME="${APP}" PYTHONPATH="${APP}/src" LOG_DIR="${LOG_DIR}" \
    HIBS_RACING_CACHE_DIR="${HIBS_RACING_CACHE_DIR}" \
    PIP_CACHE_DIR="${PIP_CACHE_DIR}" \
    HIBS_ALWAYS_SCRAPE="${HIBS_ALWAYS_SCRAPE}" \
    HIBS_RACING_SCRAPE_FORCE="${HIBS_RACING_SCRAPE_FORCE}" \
    HIBS_RACING_SCRAPE_FIRST="${HIBS_RACING_SCRAPE_FIRST}" \
    HIBS_RACING_SCRAPE_SOURCE="${HIBS_RACING_SCRAPE_SOURCE}" \
    "${PY}" "${SCRAPE_PY}"
else
  "${PY}" "${SCRAPE_PY}"
fi
