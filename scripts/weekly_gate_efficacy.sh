#!/bin/bash
# Sunday institutional gate efficacy + execution slippage ledger.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/_lib.sh"

activate_venv
load_env

WEEK_ENDED="${HIBS_WEEK_ENDED:-$(date -u +%F)}"

run_logged "weekly-gate-efficacy" \
  hibs-racing weekly-gate-efficacy --week-ended "${WEEK_ENDED}"

echo "Weekly report appended: reports/weekly_gate_efficacy.md (week ended ${WEEK_ENDED})"
