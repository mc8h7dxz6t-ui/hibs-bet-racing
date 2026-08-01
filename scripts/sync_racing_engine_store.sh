#!/usr/bin/env bash
# Automation hook: materialize engine_runner_features from scored cards.
#
#   sudo bash /opt/hibs-racing/scripts/sync_racing_engine_store.sh
set -euo pipefail

APP="${HIBS_RACING_DEPLOY_PATH:-/opt/hibs-racing}"
LOG_DIR="${LOG_DIR:-/var/log/hibs-racing}"
PY="${APP}/.venv/bin/python3"
[[ -x "${PY}" ]] || PY="python3"

[[ -d "${APP}" ]] || { echo "[engine-store] missing ${APP}" >&2; exit 0; }
mkdir -p "${LOG_DIR}"

sudo -u www-data env \
  HOME="${APP}" \
  PYTHONPATH="${APP}/src" \
  HIBS_RACING_DATA_DIR="${APP}/data" \
  "${PY}" "${APP}/scripts/sync_racing_engine_store.py" \
  | tee "${LOG_DIR}/racing-engine-store.log"
