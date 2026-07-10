#!/usr/bin/env bash
# Split diagnosis: Python import OK but https://hibs-bet.co.uk/login → 502.
#
#   sudo bash /opt/hibs-bet/scripts/vps_football_diagnose_502.sh
set -euo pipefail

BET="${DEPLOY_PATH:-/opt/hibs-bet}"
# shellcheck source=lib_racing_vps_probe.sh
source "${BET}/scripts/lib_racing_vps_probe.sh"

echo "==> football 502 split diagnosis"
football_vps_diagnose_502 "${BET}"
echo ""
echo "Next:"
echo "  sudo bash ${BET}/scripts/vps_football_hard_recovery.sh"
echo "  sudo journalctl -u hibs-bet -n 40 --no-pager"
