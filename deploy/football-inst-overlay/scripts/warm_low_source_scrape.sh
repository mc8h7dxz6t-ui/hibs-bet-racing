#!/usr/bin/env bash
# Low-source scrape cycle — FDO/FotMob/ESPN + thin rescue; backfills empty bundle.
#
#   bash /opt/hibs-bet/scripts/warm_low_source_scrape.sh
#   HIBS_LOW_SOURCE_SCRAPE_FORCE=1 bash scripts/warm_low_source_scrape.sh
set -euo pipefail

APP="${DEPLOY_PATH:-/opt/hibs-bet}"
LOG_DIR="${LOG_DIR:-/var/log/hibs-bet}"
LOCK="/var/run/hibs-bet/low-source-scrape.lock"

mkdir -p "${LOG_DIR}" /var/run/hibs-bet
cd "${APP}"

if [[ ! -x "${APP}/.venv/bin/python3" ]]; then
  echo "[low-source-scrape] ERROR: missing ${APP}/.venv/bin/python3" >&2
  exit 1
fi

exec 9>"${LOCK}"
if ! flock -n 9; then
  echo "[low-source-scrape] skip — another cycle in progress"
  exit 0
fi

export HOME="${APP}"
export PYTHONPATH="${APP}/src"
export HIBS_PRODUCTION=1
export LOG_DIR="${LOG_DIR}"

"${APP}/.venv/bin/python3" "${APP}/scripts/warm_low_source_scrape.py"
