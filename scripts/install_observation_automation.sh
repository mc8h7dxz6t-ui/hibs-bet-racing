#!/usr/bin/env bash
# One-shot: observation cron (06:00) + launchd catch-up (sleep-safe).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

bash "${SCRIPT_DIR}/install_observation_cron.sh"
bash "${SCRIPT_DIR}/install_observation_launchd.sh"
bash "${SCRIPT_DIR}/preflight_observation_lane.sh"

echo ""
echo "Institutional Mac observation automation:"
echo "  - 06:00 cron (primary)"
echo "  - hourly catch-up + on wake (launchd)"
echo "  - logs: logs/cron_daily.log + logs/observation_catchup.log"
