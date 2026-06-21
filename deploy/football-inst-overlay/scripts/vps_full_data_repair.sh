#!/usr/bin/env bash
# Repair empty football + racing data on consolidated VPS.
#
#   sudo bash /opt/hibs-bet/scripts/vps_full_data_repair.sh
# Prefer deploy copy (self-contained fallbacks):
#   sudo bash /opt/hibs-bet/deploy/vps-full-data-repair.sh
set -euo pipefail

BET="${DEPLOY_PATH:-/opt/hibs-bet}"
if [[ -f "${BET}/deploy/vps-full-data-repair.sh" ]]; then
  exec bash "${BET}/deploy/vps-full-data-repair.sh" "$@"
fi

RC=0

step() { echo ""; echo "========== $* =========="; }

[[ -d "${BET}" ]] || { echo "missing ${BET}" >&2; exit 1; }
[[ "$(id -u)" -eq 0 ]] || { echo "run as root" >&2; exit 1; }

step "Football fixtures"
if [[ -f "${BET}/scripts/vps_fixture_repair.sh" ]]; then
  bash "${BET}/scripts/vps_fixture_repair.sh" || RC=1
else
  HIBS_FIXTURE_WARM_FORCE_REFRESH=1 bash "${BET}/scripts/warm_football_fixtures.sh" || RC=1
fi

step "Racing cards"
if [[ -d "${HIBS_RACING_DEPLOY_PATH:-/opt/hibs-racing}" ]]; then
  if [[ -f "${BET}/scripts/vps_racing_repair.sh" ]]; then
    bash "${BET}/scripts/vps_racing_repair.sh" || RC=1
  else
    bash "${BET}/deploy/cron-hibs-racing-daily.sh" --run 2>/dev/null || RC=1
  fi
else
  echo "SKIP: /opt/hibs-racing not installed"
fi

step "Stack restart"
systemctl restart hibs-bet 2>/dev/null || true
systemctl restart hibs-racing 2>/dev/null || true
sleep 4

step "Quick verify"
curl -sS --max-time 8 http://127.0.0.1:8000/api/ping 2>/dev/null | head -c 120 || true
echo ""
curl -sS --max-time 8 http://127.0.0.1:5003/api/ping 2>/dev/null | head -c 120 || true
echo ""

if [[ "${RC}" -eq 0 ]]; then
  echo "========== FULL DATA REPAIR OK =========="
else
  echo "========== REPAIR FINISHED WITH WARNINGS (exit ${RC}) =========="
  echo "Football: ${BET}/.venv/bin/python3 ${BET}/scripts/diagnose_fixtures_vps.py"
  echo "Racing:   bash ${BET}/scripts/vps_racing_diagnose_cards.sh"
fi
exit "${RC}"
