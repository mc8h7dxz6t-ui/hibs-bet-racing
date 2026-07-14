#!/usr/bin/env bash
# Orchestrate racing robust scrape from hibs-bet VPS layout.
set -euo pipefail
RACING="${HIBS_RACING_DEPLOY_PATH:-/opt/hibs-racing}"
SCRIPT="${RACING}/scripts/warm_racing_scrape.sh"
[[ -f "${SCRIPT}" ]] || SCRIPT="$(cd "$(dirname "$0")/../.." && pwd)/scripts/warm_racing_scrape.sh"
export HIBS_RACING_DEPLOY_PATH="${RACING}" LOG_DIR="${LOG_DIR:-/var/log/hibs-racing}"
exec bash "${SCRIPT}"
