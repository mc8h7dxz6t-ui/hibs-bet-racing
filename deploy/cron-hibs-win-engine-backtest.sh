#!/usr/bin/env bash
# Weekly OOS McFadden backtest — seeds win_engine_calibration (does not arm engine).
#
#   sudo bash /opt/hibs-racing/deploy/cron-hibs-win-engine-backtest.sh
#   sudo bash /opt/hibs-racing/deploy/cron-hibs-win-engine-backtest.sh --install-cron
#
# Crontab example (Sunday 04:30 UTC):
#   30 4 * * 0 root bash /opt/hibs-racing/deploy/cron-hibs-win-engine-backtest.sh >> /var/log/hibs-racing/win-engine-backtest.log 2>&1
#
set -euo pipefail

RACING="${HIBS_RACING_DEPLOY_PATH:-/opt/hibs-racing}"
LOG_DIR="${LOG_DIR:-/var/log/hibs-racing}"
LOOKBACK_DAYS="${HIBS_WIN_ENGINE_BACKTEST_DAYS:-90}"
PY="${RACING}/.venv/bin/hibs-racing"

mkdir -p "${LOG_DIR}"

if [[ "${1:-}" == "--install-cron" ]]; then
  CRON_LINE="30 4 * * 0 root bash ${RACING}/deploy/cron-hibs-win-engine-backtest.sh >> ${LOG_DIR}/win-engine-backtest.log 2>&1"
  echo "${CRON_LINE}"
  echo "Add the line above to /etc/cron.d/hibs-racing or root crontab."
  exit 0
fi

[[ -x "${PY}" ]] || PY="$(command -v hibs-racing || true)"
[[ -n "${PY}" ]] || { echo "hibs-racing CLI not found under ${RACING}" >&2; exit 1; }

END="$(date -u +%Y-%m-%d)"
START="$(date -u -d "${END} - ${LOOKBACK_DAYS} days" +%Y-%m-%d 2>/dev/null || date -u -v-"${LOOKBACK_DAYS}"d +%Y-%m-%d)"

echo "==> win-engine-backtest ${START}..${END} seed-calibration"
sudo -u www-data env \
  HOME="${RACING}" \
  PYTHONPATH="${RACING}/src" \
  HIBS_RACING_DB_PATH="${RACING}/data/feature_store.sqlite" \
  "${PY}" win-engine-backtest \
  --start "${START}" \
  --end "${END}" \
  --seed-calibration \
  --compact

echo "==> done"
