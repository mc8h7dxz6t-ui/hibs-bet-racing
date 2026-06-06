#!/bin/bash
# Mac-local strict NaN / DB–UI sync check (no email). Run after refresh-cards.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/_lib.sh"

activate_venv
load_env

run_logged "data-integrity-check" \
  hibs-racing data-integrity-check --strict

echo "Data integrity OK — safe for Smart Portfolio / B2B feed."
