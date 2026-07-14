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

"${APP}/.venv/bin/python3" "${APP}/scripts/warm_racing_scrape.py"
