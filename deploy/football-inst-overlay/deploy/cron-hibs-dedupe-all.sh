#!/usr/bin/env bash
# Purge duplicate managed crons and re-verify markers.
#
#   sudo bash /opt/hibs-bet/deploy/cron-hibs-dedupe-all.sh --purge-and-verify
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/hibs-bet}"
# shellcheck source=lib_cron_dedupe.sh
source "${APP_ROOT}/deploy/lib_cron_dedupe.sh"

case "${1:---purge-and-verify}" in
  --purge-and-verify)
    hibs_crontab_purge_managed
    echo "Purged managed cron markers — reinstall with cron-hibs-ops-automation.sh --install"
    hibs_crontab_verify_managed && echo "Crontab verify: OK" || echo "WARN: duplicates remain"
    ;;
  *)
    echo "Usage: $0 --purge-and-verify"
    exit 1
    ;;
esac
