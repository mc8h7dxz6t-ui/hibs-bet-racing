#!/usr/bin/env bash
# Canonical socket helpers live in hibs-bet — source to avoid drift.
set -euo pipefail

BET_ROOT="${HIBS_BET_DEPLOY_PATH:-/opt/hibs-bet}"
CANONICAL="${BET_ROOT}/deploy/lib-racing-unix-socket.sh"
if [[ ! -f "${CANONICAL}" ]]; then
  echo "missing canonical ${CANONICAL}" >&2
  exit 1
fi
# shellcheck source=/dev/null
source "${CANONICAL}"
