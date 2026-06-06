#!/usr/bin/env bash
# Institutional++ pre-flight: env → snapshot backfill → dual-source gate audit.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/_lib.sh"

raise_fd_limit
activate_venv
load_env

START="${1:-2025-11-01}"
END="${2:-2026-05-22}"
HASH="${HIBS_SNAPSHOT_HASH:-}"

echo "=== institutional precheck ${START} → ${END} ==="

run_logged "precheck-env" python3 scripts/check_env.py

SNAP_ARGS=(--start "${START}" --end "${END}" --force)
run_logged "precheck-snapshot-backfill" hibs-racing snapshot-backfill "${SNAP_ARGS[@]}"

AUDIT_ARGS=(--start "${START}" --end "${END}" --lanes gate3,gate5,gate7 --source both)
if [[ -n "${HASH}" ]]; then
  AUDIT_ARGS+=(--snapshot-config-hash "${HASH}")
fi
run_logged "precheck-gate-coverage-audit" hibs-racing gate-coverage-audit "${AUDIT_ARGS[@]}"

run_logged "precheck-data-integrity" hibs-racing data-integrity-check --repair

echo "=== institutional precheck complete ==="
