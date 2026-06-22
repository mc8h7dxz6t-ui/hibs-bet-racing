#!/usr/bin/env bash
# Install VPS-native racing daily refresh (local consolidated box or remote SSH).
#
# Local consolidated VPS (default — no SSH):
#   sudo bash /opt/hibs-bet/scripts/install_racing_vps_cron.sh
#
# Legacy remote host:
#   DEPLOY_HOST=77.68.89.73 ./scripts/install_racing_vps_cron.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST="${DEPLOY_HOST:-}"
USER="${DEPLOY_USER:-root}"
APP="${DEPLOY_PATH:-/opt/hibs-bet}"
RACING="${HIBS_RACING_DEPLOY_PATH:-/opt/hibs-racing}"
VPS_IP="${HIBS_VPS_IP:-87.106.100.52}"

_install_local() {
  [[ -d "${RACING}" ]] || { echo "ERROR: ${RACING} missing — sync racing tree first" >&2; exit 1; }
  [[ -f "${APP}/deploy/cron-hibs-racing-daily.sh" ]] || {
    echo "ERROR: deploy/cron-hibs-racing-daily.sh missing — git pull hibs-bet" >&2
    exit 1
  }
  bash "${APP}/deploy/cron-hibs-racing-daily.sh" --install
  echo "Log: /var/log/hibs-racing/daily-refresh.log"
}

_local_host() {
  if [[ -z "${HOST}" || "${HOST}" == "local" || "${HOST}" == "127.0.0.1" || "${HOST}" == "localhost" ]]; then
    return 0
  fi
  local primary_ip=""
  primary_ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
  [[ -n "${primary_ip}" && "${HOST}" == "${primary_ip}" ]] && return 0
  [[ "${HOST}" == "${VPS_IP}" && -d "${RACING}" ]] && return 0
  return 1
}

if _local_host; then
  echo "==> Install racing VPS daily cron locally (${APP})"
  _install_local
else
  echo "==> Install racing VPS daily cron on ${USER}@${HOST}"
  ssh -o BatchMode=yes -o ConnectTimeout=25 "${USER}@${HOST}" bash -s <<REMOTE
set -euo pipefail
APP="${APP}"
RACING="${RACING}"
[[ -d "\${RACING}" ]] || { echo "ERROR: \${RACING} missing — run link_racing_production.sh first" >&2; exit 1; }
[[ -f "\${APP}/deploy/cron-hibs-racing-daily.sh" ]] || { echo "ERROR: deploy/cron-hibs-racing-daily.sh missing — git pull hibs-bet" >&2; exit 1; }
bash "\${APP}/deploy/cron-hibs-racing-daily.sh" --install
echo "Log: /var/log/hibs-racing/daily-refresh.log"
REMOTE
fi

if [[ "${RACING_VPS_CRON_SMOKE:-0}" == "1" ]]; then
  echo "==> Smoke run (RACING_VPS_CRON_SMOKE=1)"
  if _local_host; then
    bash "${APP}/deploy/cron-hibs-racing-daily.sh" --run
    tail -20 /var/log/hibs-racing/daily-refresh.log
  else
    ssh -o BatchMode=yes "${USER}@${HOST}" "sudo bash ${APP}/deploy/cron-hibs-racing-daily.sh --run"
    ssh -o BatchMode=yes "${USER}@${HOST}" "tail -20 /var/log/hibs-racing/daily-refresh.log"
  fi
fi

echo "Done. Mac deploy_racing_data_to_vps.sh is now fallback-only."
