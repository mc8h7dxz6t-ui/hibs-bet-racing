#!/usr/bin/env bash
# Hourly Brier circuit breaker — hash chain log + execution lockout on drift.
#
#   sudo bash /opt/hibs-bet/scripts/run_brier_circuit_breaker.sh
set -euo pipefail

APP="${DEPLOY_PATH:-/opt/hibs-bet}"
PY="${APP}/.venv/bin/python3"
[[ -x "${PY}" ]] || PY=python3

export HOME="${APP}" DEPLOY_PATH="${APP}" PYTHONPATH="${APP}/src:${APP}/../hibs-racing/src"
export HIBS_PRODUCTION=1

"${PY}" -c "
from hibs_predictor.safety.brier_circuit_breaker import (
    BrierCircuitBreaker,
    football_brier_compute,
    run_hourly_brier_loop,
)
import json, os

fb = run_hourly_brier_loop(
    compute_brier=football_brier_compute,
    breaker=BrierCircuitBreaker(threshold=float(os.getenv('HIBS_F10_BRIER_THRESHOLD', '0.22')), min_samples=30),
    domain='football',
)
print(json.dumps(fb, indent=2))
"

if [[ -d /opt/hibs-racing/src ]]; then
  "${PY}" -c "
from hibs_predictor.safety.brier_circuit_breaker import (
    BrierCircuitBreaker,
    racing_place_brier_compute,
    run_hourly_brier_loop,
)
import json
rc = run_hourly_brier_loop(compute_brier=racing_place_brier_compute, domain='racing')
print(json.dumps(rc, indent=2))
" || true
fi
