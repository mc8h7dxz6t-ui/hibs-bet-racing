#!/usr/bin/env bash
# Unified release gate — release-critical pytest (feeds, gate, production guards).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

PY=python3
if [[ -x "${ROOT}/.venv/bin/python" ]] && "${ROOT}/.venv/bin/python" -m pip --version &>/dev/null; then
  PY="${ROOT}/.venv/bin/python"
fi

echo "==> pip install"
"${PY}" -m pip install -q -e ".[dev,ranker,web,scraper]"

RACING_TESTS=(
  tests/test_matchbook.py
  tests/test_odds_loader.py
  tests/test_oddschecker.py
  tests/test_enrich.py
  tests/test_production_preflight.py
  tests/test_ranker_preflight.py
  tests/test_racing_engine_scoring.py
  tests/test_snapshot_store.py
  tests/test_slippage_stress.py
  tests/test_gate_regression.py
  tests/test_gate2_sensitivity.py
  tests/test_gate_benchmark_walkforward.py
  tests/test_actionability.py
  tests/test_actionability_gate2.py
  tests/test_engine_profile.py
  tests/test_log_retention.py
  tests/test_institutional.py
  tests/test_observation_lane.py
  tests/test_institutional_hardening.py
  tests/test_api_auth.py
  tests/test_ui_shell.py
  tests/test_product_links.py
  tests/test_url_prefix.py
)

echo "==> pytest (release-critical suite, ${#RACING_TESTS[@]} modules)"
"${PY}" -m pytest "${RACING_TESTS[@]}" -q --tb=short

echo "==> racing release gate GREEN"
