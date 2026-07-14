#!/usr/bin/env bash
# Racing production preflight — TIER-0 checks before cron or deploy.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

# shellcheck disable=SC1091
source "${ROOT}/scripts/_lib.sh"

activate_venv
load_env
require_ranker_artifacts

echo "==> release gate"
bash "${ROOT}/scripts/ci_release_gate.sh"

echo "==> racing production preflight GREEN"
