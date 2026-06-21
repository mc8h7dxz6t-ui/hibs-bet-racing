#!/usr/bin/env bash
# Dedupe /opt/hibs-bet/.env (last KEY wins). Safe to run from cron/watchdog.
set -euo pipefail
APP="${DEPLOY_PATH:-/opt/hibs-bet}"
# shellcheck source=lib_env_upsert.sh
source "${APP}/deploy/lib_env_upsert.sh"
[[ -f "${APP}/.env" ]] || exit 0
env_dedupe_file "${APP}/.env"
chown www-data:www-data "${APP}/.env" 2>/dev/null || true
echo "OK: deduped ${APP}/.env"
