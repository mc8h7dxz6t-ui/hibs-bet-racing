#!/usr/bin/env bash
# Warm football all_fixtures disk bundle outside gunicorn (safe for cron).
#
#   bash /opt/hibs-bet/scripts/warm_football_fixtures.sh
#   HIBS_FIXTURE_WARM_FORCE_REFRESH=1 bash scripts/warm_football_fixtures.sh
set -euo pipefail

APP="${DEPLOY_PATH:-/opt/hibs-bet}"
LOG_DIR="${LOG_DIR:-/var/log/hibs-bet}"
LOCK="/var/run/hibs-bet/fixture-warm.lock"

mkdir -p "${LOG_DIR}" /var/run/hibs-bet
cd "${APP}"

if [[ ! -x "${APP}/.venv/bin/python3" ]]; then
  echo "[fixture-warm] ERROR: missing ${APP}/.venv/bin/python3" >&2
  exit 1
fi

exec 9>"${LOCK}"
if ! flock -n 9; then
  echo "[fixture-warm] skip — another warm in progress"
  exit 0
fi

export HOME="${APP}"
export PYTHONPATH="${APP}/src"
export HIBS_PRODUCTION=1

"${APP}/.venv/bin/python3" "${APP}/scripts/warm_football_fixtures.py"
