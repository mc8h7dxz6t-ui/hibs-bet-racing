#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/_lib.sh"
activate_venv
load_env

echo "===================================================="
echo "      HIBS RACING: PURE OOS HOLDOUT REPORT          "
echo "===================================================="
echo "Evaluating Blind Window: 2026-05-01 -> 2026-05-19"
echo "Model Profile: Baseline EV + Harville Correction"
echo "----------------------------------------------------"

# Force the peak configuration environment variable flag
export HIBS_HARVILLE_CORRECTION=1

# Execute the local replay engine explicitly over the blind test matrix
hibs-racing backtest-replay --start 2026-05-01 --end 2026-05-19
