#!/usr/bin/env bash
# Phase 4+ racing integration — EW Kelly, stake sizing parity, portfolio scaling.
set -euo pipefail

APP="$(cd "$(dirname "$0")/.." && pwd)"
cd "${APP}"

PY="${APP}/.venv/bin/python3"
[[ -x "${PY}" ]] || PY="python3"

export PYTHONPATH="${APP}/src"
export HIBS_AUTOMATION_PAPER_ONLY=1

echo "[phase-4-racing] EW Kelly + stake sizing"
"${PY}" -m pytest \
  tests/test_ew_kelly.py \
  tests/test_stake_sizing.py \
  tests/test_place_kelly.py \
  -q --tb=short

echo "[phase-4-racing] OK"
